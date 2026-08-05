"""Safe, evaluation-only editing of pending OCR benchmark reference records."""

from __future__ import annotations

from copy import deepcopy
from datetime import date, datetime
import json
import os
from pathlib import Path
import tempfile


PENDING = "Pending Human Verification"
VERIFIED = "Verified"
NEEDS_REVIEW = "Needs Review"
VALID_STATUSES = {PENDING, VERIFIED, NEEDS_REVIEW}


class GroundTruthReview:
    """Keep ordered ground-truth edits, validation, backups, and saves together."""

    def __init__(self, manifest_path: str | Path, ground_truth_path: str | Path) -> None:
        self.manifest_path = Path(manifest_path)
        self.ground_truth_path = Path(ground_truth_path)
        self.manifest = self._read_json(self.manifest_path)
        self.data = self._read_json(self.ground_truth_path)
        self._validate()
        self.index = 0
        self.dirty = False

    @staticmethod
    def _read_json(path: Path) -> dict:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise ValueError(f"Malformed or unavailable JSON: {path}") from error
        if not isinstance(data, dict):
            raise ValueError(f"JSON root must be an object: {path}")
        return data

    def _validate(self) -> None:
        frames = self.manifest.get("frames")
        records = self.data.get("records")
        if not isinstance(frames, list) or not isinstance(records, list):
            raise ValueError("Manifest requires frames and ground truth requires records arrays.")
        frame_ids = [item.get("frame_id") for item in frames]
        record_ids = [item.get("frame_id") for item in records]
        if any(not isinstance(identifier, str) or not identifier for identifier in frame_ids + record_ids):
            raise ValueError("Every frame and record requires a stable frame_id.")
        if len(set(frame_ids)) != len(frame_ids) or frame_ids != record_ids:
            raise ValueError("Ground-truth records must match manifest frame IDs in order.")
        for record in records:
            if not isinstance(record.get("reference_text"), str):
                raise ValueError("Every ground-truth record requires reference_text.")
            if record.get("verification_status") not in VALID_STATUSES:
                raise ValueError("Every record requires a recognized verification_status.")
            for field in ("reviewer", "verification_date", "notes"):
                if field not in record:
                    raise ValueError(f"Every record requires {field}.")

    @property
    def record(self) -> dict:
        return self.data["records"][self.index]

    @property
    def frame(self) -> dict:
        return self.manifest["frames"][self.index]

    def update_text_and_notes(self, text: str, notes: str) -> None:
        if self.record["reference_text"] != text or self.record["notes"] != notes:
            self.record["reference_text"] = text
            self.record["notes"] = notes
            self.dirty = True

    def verify(self, reviewer: str) -> None:
        if not reviewer.strip():
            raise ValueError("A reviewer name is required to verify a record.")
        self.record.update({"verification_status": VERIFIED, "reviewer": reviewer.strip(), "verification_date": date.today().isoformat()})
        self.dirty = True

    def needs_review(self) -> None:
        self.record["verification_status"] = NEEDS_REVIEW
        self.dirty = True

    def move(self, offset: int) -> bool:
        target = self.index + offset
        if not 0 <= target < len(self.data["records"]):
            return False
        self.index = target
        return True

    def progress(self) -> dict[str, int]:
        statuses = [record["verification_status"] for record in self.data["records"]]
        return {"current": self.index + 1, "total": len(statuses), "verified": statuses.count(VERIFIED), "needs_review": statuses.count(NEEDS_REVIEW), "pending": statuses.count(PENDING)}

    def save(self) -> Path | None:
        self._validate()
        if not self.dirty:
            return None
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        backup = self.ground_truth_path.with_name(f"{self.ground_truth_path.name}.bak-{timestamp}")
        backup.write_bytes(self.ground_truth_path.read_bytes())
        descriptor, temporary = tempfile.mkstemp(prefix=f".{self.ground_truth_path.name}.", suffix=".tmp", dir=self.ground_truth_path.parent)
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as file:
                json.dump(self.data, file, ensure_ascii=False, indent=2)
                file.write("\n")
            os.replace(temporary, self.ground_truth_path)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)
        self.dirty = False
        return backup
