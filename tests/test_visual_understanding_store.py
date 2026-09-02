"""Focused tests for versioned visual-understanding JSON persistence."""

from pathlib import Path
import json
import sys
import tempfile
import unittest
from unittest.mock import patch

import numpy as np


sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from models import CandidateFrame, OCRResult
from visual_candidate_detection import (
    DETECTOR_REVISION,
    VisualAnalysisTarget,
    VisualCandidateAssessment,
    VisualCandidateDisposition,
    VisualSelectionScope,
)
from visual_evidence import project_candidate_frame_evidence
from visual_understanding_contract import (
    VisualAnalysisStatus,
    VisualAnalysisWarning,
    VisualContentType,
    VisualDetectionSignal,
    VisualRelationship,
    VisualUnderstandingResult,
    to_json_compatible,
)
from visual_understanding_pipeline import VisualUnderstandingJob, run_visual_understanding_job
from visual_understanding_store import (
    DOCUMENT_FILENAME,
    SCHEMA_NAME,
    SCHEMA_VERSION,
    VisualUnderstandingStorageError,
    load_visual_understanding_result,
    write_visual_understanding_result,
)


def target(frame_number, *, source_reference="result:module-2", slide_number=None,
           image_shape=(30, 40)):
    image = np.full((*image_shape, 3), 255, dtype=np.uint8)
    image[4:24, 8:32] = (frame_number % 255, 90, 180)
    current = CandidateFrame(
        frame_number=frame_number,
        timestamp=frame_number / 5,
        image=image,
        difference_score=0.0,
        ocr_results=[OCRResult("54% Café", 0.96, np.array([2, 2, 22, 9], dtype=float))],
    )
    evidence = project_candidate_frame_evidence(
        current,
        source_reference=source_reference,
        checkpoint_path=f"{source_reference}/cache/reading_order.pkl",
        slide_number=frame_number // 10 if slide_number is None else slide_number,
        build_index=0,
    )
    assessment = VisualCandidateAssessment(
        VisualCandidateDisposition.RECOMMENDED,
        ("dispersed_numeric_labels",),
        (VisualDetectionSignal(
            "dispersed_numeric_labels",
            "Numeric labels are spatially separated.",
            {"count": 4, "positions": ["left", "right"]},
            DETECTOR_REVISION,
        ),),
        DETECTOR_REVISION,
        "Observable structure warrants analysis.",
    )
    return VisualAnalysisTarget(evidence, assessment)


def job(*targets):
    return VisualUnderstandingJob(
        "module-2-visual",
        tuple(targets),
        VisualSelectionScope.RECOMMENDED,
        "fake-vision",
        "en",
        "visual-understanding-test-v1",
        "1.8.0-dev",
    )


class MixedProvider:
    provider_id = "fake-vision"

    def analyze(self, request):
        if request.evidence.frame_number == 20:
            return VisualUnderstandingResult(
                request,
                VisualAnalysisStatus.FAILURE,
                self.provider_id,
                model_id="fake-model",
                error="safe categorized failure",
                provider_metadata={"attempt": 1},
            )
        return VisualUnderstandingResult(
            request,
            VisualAnalysisStatus.SUCCESS,
            self.provider_id,
            model_id="fake-model",
            content_type=VisualContentType.CHART_OR_GRAPH,
            description="Café chart description.",
            relationships=(VisualRelationship("54%", "corresponds to", "Category A"),),
            structured_details={"chart_type": "pie", "values": [54, 29]},
            warnings=(VisualAnalysisWarning(
                "review_recommended", "Legend association requires review.", {"items": 1}
            ),),
            provider_metadata={"response_id": f"fake-{request.evidence.frame_number}"},
        )


class VisualUnderstandingStoreTests(unittest.TestCase):
    def setUp(self):
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary_directory.cleanup)
        self.root = Path(self.temporary_directory.name)
        self.workspace = self.root / "visual-understanding"

    def completed(self):
        return run_visual_understanding_job(job(target(10), target(20)), MixedProvider())

    def load_document(self, path):
        return json.loads(path.read_text(encoding="utf-8"))

    def write_document(self, path, document):
        path.write_text(json.dumps(document, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    def test_success_and_partial_failure_round_trip_preserve_semantics(self):
        original = self.completed()

        path = write_visual_understanding_result(original, self.workspace)
        loaded = load_visual_understanding_result(self.workspace)

        self.assertEqual((SCHEMA_NAME, SCHEMA_VERSION), (
            self.load_document(path)["schema_name"], self.load_document(path)["schema_version"],
        ))
        self.assertEqual(original.job.job_id, loaded.job.job_id)
        self.assertEqual(original.job.application_version, loaded.job.application_version)
        self.assertEqual(original.job.scope, loaded.job.scope)
        self.assertEqual((1, 1), (loaded.success_count, loaded.failure_count))
        self.assertEqual((10, 20), tuple(item.evidence.frame_number for item in loaded.results))

    def test_provider_evidence_signals_ocr_and_interpretation_round_trip(self):
        original = self.completed()
        path = write_visual_understanding_result(original, self.workspace)

        loaded = load_visual_understanding_result(path)
        success = loaded.results[0]

        self.assertEqual("fake-vision", success.provider_id)
        self.assertEqual("fake-model", success.model_id)
        self.assertEqual(original.results[0].evidence, success.evidence)
        self.assertEqual("54% Café", success.request.ocr_text)
        self.assertEqual(original.results[0].request.ocr_regions, success.request.ocr_regions)
        self.assertEqual("dispersed_numeric_labels", success.request.detection_signals[0].code)
        self.assertEqual({"count": 4, "positions": ["left", "right"]},
                         to_json_compatible(success.request.detection_signals[0].observed_values))
        self.assertEqual("Category A", success.relationships[0].object)
        self.assertEqual("pie", success.structured_details["chart_type"])
        self.assertEqual("review_recommended", success.warnings[0].code)
        self.assertEqual("fake-10", success.provider_metadata["response_id"])

    def test_failure_round_trip_has_no_fabricated_interpretation(self):
        path = write_visual_understanding_result(self.completed(), self.workspace)

        failure = load_visual_understanding_result(path).results[1]

        self.assertEqual(VisualAnalysisStatus.FAILURE, failure.status)
        self.assertIsNone(failure.content_type)
        self.assertIsNone(failure.description)
        self.assertEqual((), failure.relationships)
        self.assertEqual({}, to_json_compatible(failure.structured_details))
        self.assertEqual("safe categorized failure", failure.error)

    def test_cancelled_job_preserves_targets_without_fabricating_results(self):
        checks = iter((False, True))
        original = run_visual_understanding_job(
            job(target(10), target(20)), MixedProvider(), cancel_check=lambda: next(checks),
        )

        path = write_visual_understanding_result(original, self.workspace)
        loaded = load_visual_understanding_result(path)

        self.assertTrue(loaded.cancelled)
        self.assertEqual((1, 1), (loaded.submitted_count, loaded.unsubmitted_count))
        self.assertEqual(2, len(loaded.job.targets))
        self.assertEqual(1, len(loaded.results))
        document = self.load_document(path)
        self.assertEqual(2, len(document["targets"]))
        self.assertEqual(1, len(document["results"]))

    def test_json_is_pretty_utf8_and_preserves_result_order(self):
        path = write_visual_understanding_result(self.completed(), self.workspace)
        raw = path.read_bytes()

        self.assertIn("Café".encode("utf-8"), raw)
        self.assertIn(b"\n  \"schema_name\"", raw)
        document = self.load_document(path)
        self.assertEqual([10, 20], [item["request"]["evidence"]["frame_number"]
                                    for item in document["results"]])

    def test_evidence_png_is_written_unchanged_and_hash_verified(self):
        original = self.completed()
        path = write_visual_understanding_result(original, self.workspace)
        document = self.load_document(path)
        image_path = self.workspace / document["targets"][0]["evidence_image_path"]

        self.assertEqual(original.job.targets[0].evidence.image_bytes, image_path.read_bytes())
        loaded = load_visual_understanding_result(path, verify_evidence=True)
        self.assertEqual(original.job.targets[0].evidence.reference.authoritative_image_sha256,
                         loaded.job.targets[0].evidence.reference.authoritative_image_sha256)

    def test_transport_derivative_provenance_round_trip_preserves_authoritative_identity(self):
        original = run_visual_understanding_job(
            job(target(10, image_shape=(1080, 1920))), MixedProvider(),
        )
        reference = original.job.targets[0].evidence.reference

        path = write_visual_understanding_result(original, self.workspace)
        loaded = load_visual_understanding_result(path)
        restored = loaded.job.targets[0].evidence.reference

        self.assertEqual((1920, 1080), (restored.image_width, restored.image_height))
        self.assertEqual((1536, 864), (
            restored.submitted_image_width, restored.submitted_image_height,
        ))
        self.assertEqual(reference.authoritative_image_sha256,
                         restored.authoritative_image_sha256)
        self.assertEqual(reference.submitted_image_sha256, restored.submitted_image_sha256)
        self.assertEqual("local-vision-image-transport-v1",
                         restored.image_transport_revision)

    def test_v1_document_without_new_optional_transport_fields_still_loads(self):
        path = write_visual_understanding_result(self.completed(), self.workspace)
        document = self.load_document(path)
        for target_data in document["targets"]:
            for name in ("submitted_image_width", "submitted_image_height", "image_transport_revision"):
                target_data["evidence"].pop(name)
        for result_data in document["results"]:
            for name in ("submitted_image_width", "submitted_image_height", "image_transport_revision"):
                result_data["request"]["evidence"].pop(name)
        self.write_document(path, document)

        loaded = load_visual_understanding_result(path)

        self.assertEqual(2, len(loaded.job.targets))

    def test_corrupted_evidence_hash_is_rejected(self):
        path = write_visual_understanding_result(self.completed(), self.workspace)
        document = self.load_document(path)
        image_path = self.workspace / document["targets"][0]["evidence_image_path"]
        image_path.write_bytes(b"corrupted")

        with self.assertRaisesRegex(VisualUnderstandingStorageError, "SHA-256 mismatch"):
            load_visual_understanding_result(path)

    def test_existing_different_evidence_file_is_not_overwritten(self):
        original = self.completed()
        reference = original.job.targets[0].evidence.reference
        build = f"{reference.build_index:04d}"
        digest = reference.submitted_image_sha256 or reference.authoritative_image_sha256
        image_path = self.workspace / "evidence" / (
            f"slide_{reference.slide_number:04d}_build_{build}_"
            f"frame_{reference.frame_number:06d}_{digest[:12]}.png"
        )
        image_path.parent.mkdir(parents=True)
        image_path.write_bytes(b"different")

        with self.assertRaisesRegex(FileExistsError, "differs"):
            write_visual_understanding_result(original, self.workspace)

        self.assertEqual(b"different", image_path.read_bytes())

    def test_existing_json_is_not_silently_overwritten(self):
        original = self.completed()
        path = write_visual_understanding_result(original, self.workspace)
        before = path.read_bytes()

        with self.assertRaises(FileExistsError):
            write_visual_understanding_result(original, self.workspace)

        self.assertEqual(before, path.read_bytes())

    def test_source_checkpoint_folder_remains_untouched(self):
        source = self.root / "source-result"
        source.mkdir()
        sentinel = source / "reading_order.pkl"
        sentinel.write_bytes(b"preserved checkpoint")
        before = tuple((item.name, item.read_bytes()) for item in source.iterdir())

        write_visual_understanding_result(self.completed(), self.workspace)

        self.assertEqual(before, tuple((item.name, item.read_bytes()) for item in source.iterdir()))

    def test_unknown_version_and_wrong_schema_are_rejected(self):
        path = write_visual_understanding_result(self.completed(), self.workspace)
        document = self.load_document(path)
        document["schema_version"] = "2.0"
        self.write_document(path, document)
        with self.assertRaisesRegex(VisualUnderstandingStorageError, "schema version"):
            load_visual_understanding_result(path)

        document["schema_version"] = SCHEMA_VERSION
        document["schema_name"] = "other.schema"
        self.write_document(path, document)
        with self.assertRaisesRegex(VisualUnderstandingStorageError, "schema name"):
            load_visual_understanding_result(path)

    def test_missing_required_field_and_invalid_enum_are_rejected(self):
        path = write_visual_understanding_result(self.completed(), self.workspace)
        document = self.load_document(path)
        del document["job"]["provider_id"]
        self.write_document(path, document)
        with self.assertRaisesRegex(VisualUnderstandingStorageError, "missing required"):
            load_visual_understanding_result(path)

        document = self.load_document(write_visual_understanding_result(
            self.completed(), self.root / "second-workspace"
        ))
        document["job"]["selection_scope"] = "invented"
        second_path = self.root / "second-workspace" / "cache" / DOCUMENT_FILENAME
        self.write_document(second_path, document)
        with self.assertRaisesRegex(VisualUnderstandingStorageError, "invalid value"):
            load_visual_understanding_result(second_path)

    def test_unsupported_json_value_and_nonfinite_number_are_rejected(self):
        original = self.completed()
        object.__setattr__(original.results[0], "provider_metadata", {"path": Path("not-json")})
        with self.assertRaisesRegex(ValueError, "frozen JSON-compatible"):
            write_visual_understanding_result(original, self.workspace)

        valid = self.completed()
        path = write_visual_understanding_result(valid, self.root / "nan-workspace")
        raw = path.read_text(encoding="utf-8").replace('"attempt": 1', '"attempt": NaN')
        path.write_text(raw, encoding="utf-8")
        with self.assertRaisesRegex(VisualUnderstandingStorageError, "unsupported numeric"):
            load_visual_understanding_result(path)

    def test_storage_uses_no_pickle_and_no_processing_stages(self):
        module_source = (Path(__file__).resolve().parent.parent / "src" / "visual_understanding_store.py").read_text(encoding="utf-8")
        self.assertNotIn("import pickle", module_source)
        result = self.completed()
        with (
            patch("processing_service.perform_ocr") as ocr,
            patch("processing_service.open_video") as open_video,
            patch("processing_service.analyze_video") as analyze_video,
            patch("processing_service.reconstruct_reading_order") as reading_order,
            patch("processing_service.consolidate_slides") as consolidate,
        ):
            path = write_visual_understanding_result(result, self.workspace)
            load_visual_understanding_result(path)
        for stage in (ocr, open_video, analyze_video, reading_order, consolidate):
            stage.assert_not_called()


if __name__ == "__main__":
    unittest.main()
