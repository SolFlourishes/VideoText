"""Focused tests for read-only exact-frame visual evidence projection."""

from dataclasses import FrozenInstanceError
import hashlib
from pathlib import Path
import pickle
import sys
import unittest

import numpy as np


sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from models import CandidateFrame, OCRResult, Presentation, Slide, SlideBuild, TextLine
from visual_evidence import (
    LOCAL_VISUAL_IMAGE_TRANSPORT_REVISION,
    bounded_visual_image_transport,
    canonical_candidate_frame_image,
    project_candidate_frame_evidence,
)
from visual_understanding_contract import VisualAnalysisRequest


def candidate(image: np.ndarray | None = None) -> CandidateFrame:
    pixels = np.zeros((6, 8, 3), dtype=np.uint8) if image is None else image
    pixels[1:4, 2:6] = (10, 120, 240)
    box = np.array([2, 1, 6, 4], dtype=float)
    return CandidateFrame(
        frame_number=125,
        timestamp=25.0,
        image=pixels,
        difference_score=3.5,
        ocr_results=[OCRResult("54%", 0.97, box)],
        text_lines=[TextLine("54%", 1, 4, 2, 6, 0.97)],
    )


class VisualEvidenceTests(unittest.TestCase):
    def test_canonical_png_is_deterministic_for_identical_pixels(self):
        first_pixels = candidate().image
        second_pixels = first_pixels.copy(order="F")

        first = canonical_candidate_frame_image(first_pixels)
        second = canonical_candidate_frame_image(second_pixels)

        self.assertEqual(first.png_bytes, second.png_bytes)
        self.assertEqual(first.sha256, second.sha256)
        self.assertEqual(hashlib.sha256(first.png_bytes).hexdigest(), first.sha256)
        self.assertEqual("image/png", first.media_type)
        self.assertEqual((8, 6), (first.width, first.height))

    def test_changed_pixels_change_canonical_hash(self):
        original = candidate().image
        changed = original.copy()
        changed[0, 0] = (255, 255, 255)

        self.assertNotEqual(
            canonical_candidate_frame_image(original).sha256,
            canonical_candidate_frame_image(changed).sha256,
        )

    def test_projection_retains_context_dimensions_and_ocr_copies(self):
        frame = candidate()
        projected = project_candidate_frame_evidence(
            frame,
            source_reference="result:module-2",
            checkpoint_path=Path("module-2/cache/reading_order.pkl"),
            slide_number=3,
            build_index=1,
        )

        reference = projected.reference
        self.assertEqual((125, 25.0), (reference.frame_number, reference.timestamp))
        self.assertEqual((3, 1), (reference.slide_number, reference.build_index))
        self.assertEqual("result:module-2", reference.source_reference)
        self.assertEqual("module-2\\cache\\reading_order.pkl", reference.checkpoint_path)
        self.assertEqual((8, 6), (reference.image_width, reference.image_height))
        self.assertEqual(reference.authoritative_image_sha256, reference.submitted_image_sha256)
        self.assertEqual("54%", projected.ocr_text)
        self.assertEqual("54%", projected.ocr_regions[0].text)
        self.assertEqual((2.0, 1.0, 6.0, 4.0), projected.ocr_regions[0].bounding_box)

    def test_projection_does_not_mutate_frame_image_ocr_or_presentation(self):
        frame = candidate()
        presentation = Presentation(
            metadata={"source": "preserved"},
            slides=[Slide(3, 25.0, 25.0, builds=[SlideBuild([frame], "54%")])],
            statistics={"slides": 1},
        )
        frame_before = pickle.dumps(frame)
        presentation_before = pickle.dumps(presentation)

        projected = project_candidate_frame_evidence(
            frame,
            source_reference="result:module-2",
            slide_number=3,
            build_index=0,
        )

        self.assertEqual(frame_before, pickle.dumps(frame))
        self.assertEqual(presentation_before, pickle.dumps(presentation))
        self.assertIs(frame, presentation.slides[0].builds[0].candidate_frames[0])
        with self.assertRaises(FrozenInstanceError):
            projected.ocr_regions[0].text = "changed"

    def test_projection_is_detached_from_later_ocr_mutation(self):
        frame = candidate()
        projected = project_candidate_frame_evidence(
            frame, source_reference="result:module-2", slide_number=3,
        )

        frame.ocr_results[0].text = "changed later"
        frame.ocr_results[0].bounding_box[0] = 99

        self.assertEqual("54%", projected.ocr_regions[0].text)
        self.assertEqual(2.0, projected.ocr_regions[0].bounding_box[0])

    def test_projection_builds_a_hash_valid_analysis_request(self):
        projected = project_candidate_frame_evidence(
            candidate(), source_reference="result:module-2", slide_number=3,
        )

        request = VisualAnalysisRequest(
            request_id="module-2:slide:3:frame:125",
            evidence=projected.reference,
            image_bytes=projected.image_bytes,
            image_media_type=projected.image_media_type,
            ocr_text=projected.ocr_text,
            ocr_regions=projected.ocr_regions,
        )

        self.assertEqual(projected.reference, request.evidence)

    def test_invalid_frame_image_is_rejected_without_fallback(self):
        frame = candidate()
        frame.image = None

        with self.assertRaisesRegex(ValueError, "NumPy array"):
            project_candidate_frame_evidence(
                frame, source_reference="result:module-2", slide_number=3,
            )

    def test_large_image_uses_deterministic_aspect_preserving_transport_derivative(self):
        pixels = np.zeros((1080, 1920, 3), dtype=np.uint8)
        pixels[100:900, 200:1700] = (20, 140, 230)
        frame = candidate(pixels)
        source_before = frame.image.tobytes()

        first = project_candidate_frame_evidence(
            frame, source_reference="result:module-2", slide_number=3,
        )
        second = project_candidate_frame_evidence(
            frame, source_reference="result:module-2", slide_number=3,
        )

        self.assertEqual((1920, 1080), (
            first.reference.image_width, first.reference.image_height,
        ))
        self.assertEqual((1536, 864), (
            first.reference.submitted_image_width, first.reference.submitted_image_height,
        ))
        self.assertNotEqual(
            first.reference.authoritative_image_sha256,
            first.reference.submitted_image_sha256,
        )
        self.assertEqual(LOCAL_VISUAL_IMAGE_TRANSPORT_REVISION,
                         first.reference.image_transport_revision)
        self.assertEqual(first.image_bytes, second.image_bytes)
        self.assertEqual(first.reference.submitted_image_sha256,
                         second.reference.submitted_image_sha256)
        self.assertEqual(source_before, frame.image.tobytes())
        self.assertEqual("54%", first.ocr_text)

    def test_transport_does_not_resize_below_threshold(self):
        canonical = canonical_candidate_frame_image(candidate().image)
        transported = bounded_visual_image_transport(canonical, maximum_dimension=1536)

        self.assertIs(canonical, transported)


if __name__ == "__main__":
    unittest.main()
