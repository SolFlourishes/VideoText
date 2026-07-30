"""Optional, read-only diagnostic exports for VideoText OCR evidence."""

from __future__ import annotations

from dataclasses import dataclass, field
import json
from pathlib import Path
from typing import Any

from app_info import APP_NAME, APP_RELEASE
from config import OCR_LANGUAGE


DIAGNOSTIC_SCHEMA_VERSION = "1.0"


class DiagnosticError(RuntimeError):
    """Raised when a requested diagnostic export cannot be completed."""


@dataclass(frozen=True)
class DiagnosticOptions:
    """Selection and write policy for one diagnostic run."""

    output_directory: Path
    all_candidate_frames: bool = False
    frame_indices: frozenset[int] = frozenset()
    slide_numbers: frozenset[int] = frozenset()
    low_confidence_threshold: float = 0.80
    overwrite: bool = False
    strict: bool = False


@dataclass(frozen=True)
class OCRDiagnosticRegion:
    """Immutable OCR-region evidence captured in original OCR sequence."""

    region_id: str
    source_index: int
    reading_order_index: int | None
    bounding_box: list[float]
    recognized_text: str
    confidence: float | None
    line_id: int | None = None
    within_line_position: int | None = None
    suppressed_as_overlap_duplicate: bool = False
    suppression_reason: str | None = None
    flags: tuple[str, ...] = ()


@dataclass
class OCRDiagnosticFrame:
    """Frame evidence gathered at OCR and reconstruction stage boundaries."""

    frame_index: int
    timestamp: float | None
    image: Any
    regions: list[OCRDiagnosticRegion]
    raw_text: str
    ordered_text: str = ""
    reconstructed_text: str = ""
    reconstructed_lines: list[str] = field(default_factory=list)
    paragraphs: list[str] = field(default_factory=list)
    associated_slide_number: int | None = None
    warnings: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class OCRDiagnosticSlide:
    """Available pre- and post-consolidation text for one final slide."""

    slide_number: int
    contributing_frame_indices: tuple[int, ...]
    pre_consolidation_text: str
    post_consolidation_text: str


def _box_values(box: Any) -> list[float]:
    """Serialize existing rectangular OCR box data without altering it."""

    values = box.tolist() if hasattr(box, "tolist") else list(box)
    return [float(value) for value in values]


def _region_signature(result: Any) -> tuple[str, float | None, tuple[float, ...]]:
    confidence = getattr(result, "confidence", None)
    return (
        str(getattr(result, "text", "")),
        None if confidence is None else float(confidence),
        tuple(_box_values(getattr(result, "bounding_box", ()))),
    )


def _write_text(path: Path, text: str) -> None:
    path.write_text(text, encoding="utf-8")


class OCRDiagnosticsWriter:
    """Collect immutable stage snapshots and write deterministic diagnostics."""

    def __init__(self, options: DiagnosticOptions, source_description: str) -> None:
        if not 0 <= options.low_confidence_threshold <= 1:
            raise DiagnosticError("Low-confidence threshold must be between 0 and 1.")
        if not (options.all_candidate_frames or options.frame_indices or options.slide_numbers):
            raise DiagnosticError("Select all candidate frames, frame indices, or slide numbers.")
        self.options = options
        self.source_description = source_description
        self.frames: dict[int, OCRDiagnosticFrame] = {}
        self.slides: list[OCRDiagnosticSlide] = []
        self.run_warnings: list[str] = []
        self.failures: list[str] = []

    def capture_ocr_frames(self, candidate_frames) -> None:
        """Snapshot the original OCR sequence immediately after OCR completes."""

        for frame in candidate_frames:
            regions = []
            for source_index, result in enumerate(frame.ocr_results, start=1):
                confidence = getattr(result, "confidence", None)
                flags = []
                if confidence is None:
                    flags.append("confidence_unavailable")
                elif float(confidence) < self.options.low_confidence_threshold:
                    flags.append("low_confidence")
                regions.append(OCRDiagnosticRegion(
                    region_id=f"region_{source_index:03d}",
                    source_index=source_index,
                    reading_order_index=None,
                    bounding_box=_box_values(result.bounding_box),
                    recognized_text=str(result.text),
                    confidence=None if confidence is None else float(confidence),
                    flags=tuple(flags),
                ))
            self.frames[frame.frame_number] = OCRDiagnosticFrame(
                frame_index=frame.frame_number,
                timestamp=getattr(frame, "timestamp", None),
                image=frame.image.copy(),
                regions=regions,
                raw_text="\n".join(region.recognized_text for region in regions),
            )

    def capture_reconstructed_frames(self, candidate_frames, raw_sequence_available: bool = True) -> None:
        """Add actual post-reading-order lines and paragraphs to frame snapshots."""

        for frame in candidate_frames:
            diagnostic_frame = self.frames.get(frame.frame_number)
            if diagnostic_frame is None:
                # A reading-order replay has no preserved raw OCR sequence.
                self.capture_ocr_frames([frame])
                diagnostic_frame = self.frames[frame.frame_number]
                if not raw_sequence_available:
                    diagnostic_frame.warnings.append("Raw OCR sequence was unavailable in the selected checkpoint.")
                    warning = "Raw OCR sequence is unavailable when diagnostics start from a reading-order checkpoint."
                    if warning not in self.run_warnings:
                        self.run_warnings.append(warning)
            current_indices: dict[tuple[str, float | None, tuple[float, ...]], list[int]] = {}
            line_metadata = {
                tuple(item.bounding_box): item
                for item in getattr(frame, "line_reconstruction_metadata", [])
            }
            for reading_order_index, result in enumerate(frame.ocr_results, start=1):
                current_indices.setdefault(_region_signature(result), []).append(reading_order_index)
            updated_regions = []
            for region in diagnostic_frame.regions:
                signature = (region.recognized_text, region.confidence, tuple(region.bounding_box))
                positions = current_indices.get(signature, [])
                reading_order_index = positions.pop(0) if positions else None
                flags = list(region.flags)
                if reading_order_index is None:
                    flags.append("not_in_reading_order")
                metadata = line_metadata.get(tuple(region.bounding_box))
                updated_regions.append(OCRDiagnosticRegion(
                    region_id=region.region_id,
                    source_index=region.source_index,
                    reading_order_index=reading_order_index,
                    bounding_box=list(region.bounding_box),
                    recognized_text=region.recognized_text,
                    confidence=region.confidence,
                    line_id=None if metadata is None else metadata.line_id,
                    within_line_position=None if metadata is None else metadata.within_line_position,
                    suppressed_as_overlap_duplicate=False if metadata is None else metadata.suppressed,
                    suppression_reason=None if metadata is None else metadata.suppression_reason,
                    flags=tuple(flags),
                ))
            diagnostic_frame.regions = updated_regions
            diagnostic_frame.ordered_text = "\n".join(result.text for result in frame.ocr_results)
            diagnostic_frame.reconstructed_lines = [line.text for line in frame.text_lines]
            diagnostic_frame.paragraphs = [paragraph.text for paragraph in frame.text_paragraphs]
            diagnostic_frame.reconstructed_text = "\n".join(diagnostic_frame.paragraphs)

    def capture_slides(self, slides) -> None:
        """Record only the existing build and canonical paragraph text."""

        self.slides = []
        for slide in slides:
            frame_indices = tuple(
                frame.frame_number
                for build in slide.builds
                for frame in build.candidate_frames
            )
            self.slides.append(OCRDiagnosticSlide(
                slide_number=slide.slide_number,
                contributing_frame_indices=frame_indices,
                pre_consolidation_text="\n\n".join(build.final_text for build in slide.builds),
                post_consolidation_text="\n".join(paragraph.text for paragraph in slide.paragraphs),
            ))
            for frame_index in frame_indices:
                if frame_index in self.frames:
                    self.frames[frame_index].associated_slide_number = slide.slide_number

    def _selected_frame_indices(self) -> list[int]:
        available = set(self.frames)
        selected = set(self.options.frame_indices)
        if self.options.all_candidate_frames:
            selected.update(available)
        if self.options.slide_numbers:
            for slide in self.slides:
                if slide.slide_number in self.options.slide_numbers:
                    selected.update(slide.contributing_frame_indices)
        missing = sorted(selected - available)
        if missing:
            message = "Requested candidate frames were not found: " + ", ".join(map(str, missing))
            if self.options.strict:
                raise DiagnosticError(message)
            self.run_warnings.append(message)
        return sorted(selected & available)

    def _write_image(self, path: Path, image: Any) -> None:
        import cv2

        if not cv2.imwrite(str(path), image):
            raise DiagnosticError(f"Could not write diagnostic image: {path}")

    def _overlay(self, frame: OCRDiagnosticFrame, reading_order: bool) -> Any:
        import cv2

        image = frame.image.copy()
        for region in frame.regions:
            values = region.bounding_box
            if len(values) < 4:
                continue
            left, top, right, bottom = (round(value) for value in values[:4])
            color = (0, 165, 255) if "low_confidence" in region.flags else (0, 220, 0)
            cv2.rectangle(image, (left, top), (right, bottom), color, 2)
            label = (
                str(region.reading_order_index)
                if reading_order and region.reading_order_index is not None
                else region.region_id
            )
            if not reading_order and region.confidence is not None:
                label += f" {region.confidence:.2f}"
            cv2.putText(image, label, (left, max(14, top - 4)), cv2.FONT_HERSHEY_SIMPLEX, 0.45, color, 1, cv2.LINE_AA)
        return image

    def _regions_data(self, frame: OCRDiagnosticFrame, relative_paths: dict[str, str]) -> dict:
        confidences = [region.confidence for region in frame.regions if region.confidence is not None]
        return {
            "schema_version": DIAGNOSTIC_SCHEMA_VERSION,
            "frame_index": frame.frame_index,
            "timestamp": frame.timestamp,
            "source_frame_path": relative_paths["original"],
            "preprocessing_image_path": relative_paths["ocr_input"],
            "ocr_input_note": "The current OCR pipeline receives the candidate frame image unchanged.",
            "original_ocr_sequence": [region.region_id for region in frame.regions],
            "reading_order_sequence": [region.region_id for region in frame.regions if region.reading_order_index is not None],
            "regions": [
                {
                    "region_id": region.region_id,
                    "source_index": region.source_index,
                    "reading_order_index": region.reading_order_index,
                    "bounding_box": region.bounding_box,
                    "recognized_text": region.recognized_text,
                    "confidence": region.confidence,
                    "line_id": region.line_id,
                    "within_line_position": region.within_line_position,
                    "suppressed_as_overlap_duplicate": region.suppressed_as_overlap_duplicate,
                    "suppression_reason": region.suppression_reason,
                    "flags": list(region.flags),
                }
                for region in frame.regions
            ],
            "reconstructed_lines": frame.reconstructed_lines,
            "paragraphs": frame.paragraphs,
            "associated_slide_number": frame.associated_slide_number,
            "confidence_summary": {
                "count": len(confidences),
                "average": sum(confidences) / len(confidences) if confidences else None,
                "minimum": min(confidences) if confidences else None,
                "below_threshold": sum(value < self.options.low_confidence_threshold for value in confidences),
                "threshold": self.options.low_confidence_threshold,
            },
            "warnings": frame.warnings,
        }

    def write(self, run_directory: Path | None = None) -> list[Path]:
        """Write selected frame/slide evidence and deterministic run reports."""

        output_directory = self.options.output_directory
        if output_directory.exists() and any(output_directory.iterdir()) and not self.options.overwrite:
            raise DiagnosticError(f"Diagnostic output already exists: {output_directory}. Use overwrite to replace it.")
        output_directory.mkdir(parents=True, exist_ok=True)
        selected_indices = self._selected_frame_indices()
        files: list[Path] = []
        frame_entries = []
        for frame_index in selected_indices:
            frame = self.frames[frame_index]
            frame_directory = output_directory / "frames" / f"frame_{frame_index:06d}"
            frame_directory.mkdir(parents=True, exist_ok=True)
            paths = {
                "original": frame_directory / "original.png",
                "ocr_input": frame_directory / "ocr_input.png",
                "regions": frame_directory / "regions.png",
                "reading_order": frame_directory / "reading_order.png",
                "regions_json": frame_directory / "regions.json",
                "raw_text": frame_directory / "raw_text.txt",
                "ordered_text": frame_directory / "ordered_text.txt",
                "reconstructed_text": frame_directory / "reconstructed_text.txt",
            }
            self._write_image(paths["original"], frame.image)
            self._write_image(paths["ocr_input"], frame.image)
            self._write_image(paths["regions"], self._overlay(frame, reading_order=False))
            self._write_image(paths["reading_order"], self._overlay(frame, reading_order=True))
            relative_paths = {key: path.relative_to(output_directory).as_posix() for key, path in paths.items() if key in {"original", "ocr_input"}}
            paths["regions_json"].write_text(json.dumps(self._regions_data(frame, relative_paths), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            _write_text(paths["raw_text"], frame.raw_text)
            _write_text(paths["ordered_text"], frame.ordered_text)
            _write_text(paths["reconstructed_text"], frame.reconstructed_text)
            files.extend(paths.values())
            frame_entries.append({
                "frame_index": frame_index,
                "slide_number": frame.associated_slide_number,
                "path": frame_directory.relative_to(output_directory).as_posix(),
                "region_count": len(frame.regions),
            })
        selected_frame_set = set(selected_indices)
        exported_slides = []
        slide_entries = []
        for slide in self.slides:
            include_slide = (
                self.options.all_candidate_frames
                or slide.slide_number in self.options.slide_numbers
                or bool(selected_frame_set.intersection(slide.contributing_frame_indices))
            )
            if not include_slide:
                continue
            slide_directory = output_directory / "slides" / f"slide_{slide.slide_number:04d}"
            slide_directory.mkdir(parents=True, exist_ok=True)
            slide_path = slide_directory / "slide.json"
            pre_path = slide_directory / "pre_consolidation.txt"
            final_path = slide_directory / "final_text.txt"
            slide_data = {
                "schema_version": DIAGNOSTIC_SCHEMA_VERSION,
                "slide_number": slide.slide_number,
                "contributing_frame_indices": list(slide.contributing_frame_indices),
                "pre_consolidation_text": slide.pre_consolidation_text,
                "post_consolidation_text": slide.post_consolidation_text,
            }
            slide_path.write_text(json.dumps(slide_data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            _write_text(pre_path, slide.pre_consolidation_text)
            _write_text(final_path, slide.post_consolidation_text)
            files.extend((slide_path, pre_path, final_path))
            slide_entries.append({"slide_number": slide.slide_number, "path": slide_directory.relative_to(output_directory).as_posix()})
            exported_slides.append(slide)
        run_data = {
            "schema_version": DIAGNOSTIC_SCHEMA_VERSION,
            "application": {"name": APP_NAME, "release": APP_RELEASE},
            "source": self.source_description,
            "run_directory": None if run_directory is None else str(run_directory),
            "selected_scope": {
                "all_candidate_frames": self.options.all_candidate_frames,
                "frame_indices": sorted(self.options.frame_indices),
                "slide_numbers": sorted(self.options.slide_numbers),
                "low_confidence_threshold": self.options.low_confidence_threshold,
            },
            "settings": {"ocr_language": OCR_LANGUAGE, "ocr_input": "candidate image unchanged"},
            "frames": frame_entries,
            "slides": slide_entries,
            "warnings": self.run_warnings,
            "failures": self.failures,
        }
        run_path = output_directory / "run.json"
        run_path.write_text(json.dumps(run_data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        summary_path = output_directory / "summary.md"
        summary_lines = ["# VideoText OCR Diagnostics", "", f"Source: {self.source_description}", "", "## Selected frames", ""]
        for entry in frame_entries:
            frame = self.frames[entry["frame_index"]]
            confidences = [region.confidence for region in frame.regions if region.confidence is not None]
            average = "n/a" if not confidences else f"{sum(confidences) / len(confidences):.2%}"
            minimum = "n/a" if not confidences else f"{min(confidences):.2%}"
            low = sum(value < self.options.low_confidence_threshold for value in confidences)
            summary_lines.append(f"- [Frame {entry['frame_index']}]({entry['path']}/regions.json): {entry['region_count']} regions, average confidence {average}, minimum {minimum}, {low} below threshold")
        summary_lines.extend(["", "## Slide mapping", ""])
        summary_lines.extend(f"- Slide {slide.slide_number}: frames {', '.join(map(str, slide.contributing_frame_indices))}" for slide in exported_slides)
        if self.run_warnings or self.failures:
            summary_lines.extend(["", "## Warnings and failures", ""])
            summary_lines.extend(f"- {warning}" for warning in self.run_warnings + self.failures)
        summary_path.write_text("\n".join(summary_lines) + "\n", encoding="utf-8")
        files.extend((run_path, summary_path))
        return files
