"""Focused tests for provider-neutral visual-understanding contracts."""

from dataclasses import FrozenInstanceError, fields
import hashlib
import json
from pathlib import Path
import sys
import unittest


sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from visual_understanding_contract import (
    VisualAnalysisRequest,
    VisualAnalysisStatus,
    VisualAnalysisWarning,
    VisualContentType,
    VisualDetectionSignal,
    VisualEvidenceReference,
    VisualOCRRegion,
    VisualRelationship,
    VisualUnderstandingProvider,
    VisualUnderstandingResult,
    freeze_json_value,
    to_json_compatible,
)


IMAGE_BYTES = b"canonical png bytes"
IMAGE_HASH = hashlib.sha256(IMAGE_BYTES).hexdigest()


def evidence() -> VisualEvidenceReference:
    return VisualEvidenceReference(
        source_reference="result:module-2",
        checkpoint_path=r"D:\results\cache\reading_order.pkl",
        slide_number=3,
        build_index=1,
        frame_number=125,
        timestamp=25.0,
        image_width=640,
        image_height=360,
        authoritative_image_sha256=IMAGE_HASH,
        submitted_image_sha256=IMAGE_HASH,
    )


def request() -> VisualAnalysisRequest:
    return VisualAnalysisRequest(
        request_id="module-2:slide:3:frame:125",
        evidence=evidence(),
        image_bytes=IMAGE_BYTES,
        image_media_type="image/png",
        ocr_text="Spiritual 54%",
        ocr_regions=(VisualOCRRegion(0, "54%", 0.97, (10.0, 20.0, 40.0, 35.0)),),
        detection_signals=(VisualDetectionSignal(
            "dispersed_numeric_labels",
            "Numeric labels are spatially separated.",
            {"label_count": 4, "positions": ["left", "right"]},
            "visual-detection-v1",
        ),),
    )


class FakeProvider:
    provider_id = "fake-vision"

    def analyze(self, value: VisualAnalysisRequest) -> VisualUnderstandingResult:
        return VisualUnderstandingResult(
            request=value,
            status=VisualAnalysisStatus.SUCCESS,
            provider_id=self.provider_id,
            model_id="fake-model",
            content_type=VisualContentType.CHART_OR_GRAPH,
            description="A pie chart associates categories with percentages.",
            relationships=(VisualRelationship("Spiritual", "has value", "54%"),),
            structured_details={"chart_type": "pie", "values": [54, 29, 9, 8]},
            warnings=(VisualAnalysisWarning(
                "legend_ambiguous", "One legend association may require review."
            ),),
            provider_metadata={"response_id": "fake-1"},
        )


class VisualUnderstandingContractTests(unittest.TestCase):
    def test_small_content_taxonomy_is_stable(self):
        self.assertEqual(
            {
                "text_only", "chart_or_graph", "diagram_or_process", "table",
                "meaningful_figure_or_photo", "decorative_or_background",
                "mixed_or_uncertain",
            },
            {value.value for value in VisualContentType},
        )

    def test_evidence_retains_exact_source_and_frame_provenance(self):
        value = evidence()

        self.assertEqual("result:module-2", value.source_reference)
        self.assertEqual(r"D:\results\cache\reading_order.pkl", value.checkpoint_path)
        self.assertEqual((3, 1), (value.slide_number, value.build_index))
        self.assertEqual((125, 25.0), (value.frame_number, value.timestamp))
        self.assertEqual((640, 360), (value.image_width, value.image_height))
        self.assertEqual(IMAGE_HASH, value.authoritative_image_sha256)

    def test_contracts_are_immutable(self):
        value = request()
        with self.assertRaises(FrozenInstanceError):
            value.ocr_text = "changed"
        with self.assertRaises(TypeError):
            value.detection_signals[0].observed_values["label_count"] = 5

    def test_json_values_are_deeply_frozen_and_serializable_through_helper(self):
        frozen = freeze_json_value({"items": [{"value": 1}], "valid": True})
        with self.assertRaises(TypeError):
            frozen["items"][0]["value"] = 2

        serialized = json.dumps(to_json_compatible(frozen), allow_nan=False, sort_keys=True)

        self.assertEqual('{"items": [{"value": 1}], "valid": true}', serialized)

    def test_non_json_values_are_rejected_for_contract_metadata(self):
        with self.assertRaisesRegex(ValueError, "non-JSON-compatible"):
            VisualDetectionSignal("observable", "Observed evidence.", {"path": Path("x")})
        with self.assertRaisesRegex(ValueError, "non-finite"):
            VisualAnalysisWarning("ambiguous", "Needs review.", {"value": float("nan")})

    def test_detection_signals_are_observations_not_confidence(self):
        signal = request().detection_signals[0]

        self.assertEqual("dispersed_numeric_labels", signal.code)
        self.assertIn("spatially separated", signal.explanation)
        self.assertNotIn("confidence", {item.name for item in fields(VisualDetectionSignal)})

    def test_warnings_do_not_expose_calibrated_confidence(self):
        warning = VisualAnalysisWarning("ambiguous", "Relationship requires review.")

        self.assertNotIn("confidence", {item.name for item in fields(VisualAnalysisWarning)})
        self.assertEqual("ambiguous", warning.code)

    def test_fake_provider_satisfies_protocol_and_preserves_request(self):
        provider = FakeProvider()
        source_request = request()

        result = provider.analyze(source_request)

        self.assertIsInstance(provider, VisualUnderstandingProvider)
        self.assertIs(source_request, result.request)
        self.assertIs(source_request.evidence, result.evidence)
        self.assertEqual("fake-vision", result.provider_id)
        self.assertEqual("pie", result.structured_details["chart_type"])

    def test_failure_preserves_provenance_without_interpretation(self):
        source_request = request()
        result = VisualUnderstandingResult(
            request=source_request,
            status=VisualAnalysisStatus.FAILURE,
            provider_id="fake-vision",
            model_id="fake-model",
            error="provider request failed",
            provider_metadata={"attempt": 1},
        )

        self.assertIs(source_request.evidence, result.evidence)
        self.assertIsNone(result.content_type)
        self.assertIsNone(result.description)
        self.assertEqual((), result.relationships)
        self.assertEqual({}, to_json_compatible(result.structured_details))

    def test_failed_result_rejects_fabricated_interpretation(self):
        with self.assertRaisesRegex(ValueError, "fabricated interpretation"):
            VisualUnderstandingResult(
                request=request(),
                status=VisualAnalysisStatus.FAILURE,
                provider_id="fake-vision",
                content_type=VisualContentType.CHART_OR_GRAPH,
                description="Invented",
                error="provider request failed",
            )


if __name__ == "__main__":
    unittest.main()
