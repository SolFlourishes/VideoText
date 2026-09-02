"""Deterministic synthetic-fixture tests for visual candidate triage."""

from dataclasses import fields
from pathlib import Path
import pickle
import sys
import unittest

import cv2
import numpy as np


sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from models import CandidateFrame, OCRResult, Presentation, Slide, SlideBuild
from visual_candidate_detection import (
    DETECTOR_REVISION,
    VisualCandidateAssessment,
    VisualCandidateDisposition,
    VisualSelectionScope,
    assess_visual_candidate,
    select_visual_analysis_targets,
)
from visual_understanding_contract import to_json_compatible


def region(text, box, confidence=0.95):
    return OCRResult(text, confidence, np.array(box, dtype=float))


def frame(number, image, regions=(), timestamp=None):
    return CandidateFrame(
        frame_number=number,
        timestamp=number / 5 if timestamp is None else timestamp,
        image=image,
        difference_score=0.0,
        ocr_results=list(regions),
    )


def signal(assessment, code):
    return next((value for value in assessment.signals if value.code == code), None)


def text_only_frame(number=10):
    image = np.full((200, 320, 3), 255, dtype=np.uint8)
    regions = []
    for index in range(6):
        top = 10 + index * 30
        regions.append(region(f"Long text line {index}", (10, top, 310, top + 24)))
    return frame(number, image, regions)


def pie_like_frame(number=20):
    image = np.full((240, 320, 3), 255, dtype=np.uint8)
    cv2.circle(image, (160, 125), 75, (0, 0, 0), 3)
    for endpoint in ((160, 50), (225, 160), (100, 180), (95, 75)):
        cv2.line(image, (160, 125), endpoint, (0, 0, 0), 2)
    regions = (
        region("54%", (35, 40, 70, 58)),
        region("29%", (250, 65, 290, 83)),
        region("9%", (245, 190, 275, 208)),
        region("8%", (30, 185, 60, 203)),
    )
    return frame(number, image, regions)


def time_series_like_frame(number=30):
    image = np.full((240, 360, 3), 255, dtype=np.uint8)
    for y in (40, 80, 120, 160, 200):
        cv2.line(image, (45, y), (340, y), (160, 160, 160), 1)
    cv2.line(image, (45, 25), (45, 205), (0, 0, 0), 2)
    points = np.array([(50, 180), (115, 145), (185, 125), (255, 75), (330, 55)])
    cv2.polylines(image, [points], False, (0, 0, 0), 3)
    regions = (
        region("1940", (42, 210, 78, 226)),
        region("1960", (110, 210, 146, 226)),
        region("1980", (180, 210, 216, 226)),
        region("2000", (250, 210, 286, 226)),
        region("2020", (320, 210, 356, 226)),
        region("50%", (5, 35, 38, 52)),
    )
    return frame(number, image, regions)


def diagram_like_frame(number=40):
    image = np.full((220, 340, 3), 255, dtype=np.uint8)
    boxes = ((20, 80, 90, 130), (135, 25, 205, 75), (245, 80, 315, 130), (135, 150, 205, 200))
    for box in boxes:
        cv2.rectangle(image, box[:2], box[2:], (0, 0, 0), 2)
    cv2.line(image, (90, 105), (135, 50), (0, 0, 0), 3)
    cv2.line(image, (205, 50), (245, 105), (0, 0, 0), 3)
    cv2.line(image, (280, 130), (205, 175), (0, 0, 0), 3)
    cv2.line(image, (135, 175), (55, 130), (0, 0, 0), 3)
    return frame(number, image, (
        region("Start", (30, 93, 75, 111)),
        region("Review", (252, 93, 307, 111)),
    ))


class VisualCandidateDetectionTests(unittest.TestCase):
    def test_ocr_coverage_and_large_non_text_area_are_observable(self):
        image = np.full((100, 100, 3), 255, dtype=np.uint8)
        assessment = assess_visual_candidate(frame(1, image, (region("Area", (0, 0, 50, 50)),)))
        coverage = signal(assessment, "ocr_coverage")

        self.assertAlmostEqual(0.25, coverage.observed_values["coverage_ratio"])
        self.assertIsNotNone(signal(assessment, "large_non_text_region"))

    def test_sparse_and_dense_text_signals(self):
        sparse = assess_visual_candidate(frame(
            1, np.full((100, 100, 3), 255, dtype=np.uint8),
            (region("Label", (5, 5, 20, 15)),),
        ))
        dense = assess_visual_candidate(text_only_frame())

        self.assertIsNotNone(signal(sparse, "sparse_text"))
        self.assertIsNotNone(signal(dense, "dense_text"))
        self.assertEqual(VisualCandidateDisposition.TEXT_DOMINANT, dense.disposition)

    def test_pie_like_fixture_is_recommended_from_numeric_dispersion(self):
        assessment = assess_visual_candidate(pie_like_frame())
        numeric = signal(assessment, "dispersed_numeric_labels")

        self.assertEqual(VisualCandidateDisposition.RECOMMENDED, assessment.disposition)
        self.assertIsNotNone(numeric)
        self.assertEqual(4, numeric.observed_values["percentage_count"])

    def test_time_series_fixture_has_year_percentage_and_linear_evidence(self):
        assessment = assess_visual_candidate(time_series_like_frame())
        numeric = signal(assessment, "dispersed_numeric_labels")

        self.assertEqual(VisualCandidateDisposition.RECOMMENDED, assessment.disposition)
        self.assertEqual(5, numeric.observed_values["year_count"])
        self.assertEqual(1, numeric.observed_values["percentage_count"])
        self.assertIsNotNone(signal(assessment, "repeated_linear_structure"))

    def test_diagram_like_fixture_is_recommended_without_semantic_claim(self):
        assessment = assess_visual_candidate(diagram_like_frame())

        self.assertEqual(VisualCandidateDisposition.RECOMMENDED, assessment.disposition)
        self.assertIsNotNone(signal(assessment, "repeated_linear_structure"))
        self.assertNotIn("content_type", {item.name for item in fields(VisualCandidateAssessment)})
        self.assertNotIn("diagram", assessment.explanation.casefold())

    def test_photo_like_sparse_ocr_is_not_automatically_excluded(self):
        generator = np.random.default_rng(42)
        image = generator.integers(0, 256, (180, 260, 3), dtype=np.uint8)
        assessment = assess_visual_candidate(frame(50, image))

        self.assertNotEqual(VisualCandidateDisposition.TEXT_DOMINANT, assessment.disposition)
        self.assertTrue(assessment.analyzable)

    def test_blank_uncertain_frame_remains_analyzable(self):
        image = np.full((100, 160, 3), 255, dtype=np.uint8)
        assessment = assess_visual_candidate(frame(60, image))

        self.assertEqual(VisualCandidateDisposition.UNCERTAIN, assessment.disposition)
        self.assertTrue(assessment.analyzable)

    def test_default_uses_latest_final_build_frame(self):
        first = frame(10, np.full((80, 120, 3), 245, dtype=np.uint8))
        latest = frame(20, np.full((80, 120, 3), 240, dtype=np.uint8))
        slide = Slide(1, 2.0, 4.0, builds=[SlideBuild([first, latest], "same")])
        presentation = Presentation(slides=[slide])

        targets = select_visual_analysis_targets(
            presentation, source_reference="result:one", scope=VisualSelectionScope.ALL_SLIDES,
        )

        self.assertEqual((20,), tuple(target.frame_number for target in targets))

    def test_materially_different_visual_states_are_both_retained(self):
        first = frame(10, np.zeros((80, 120, 3), dtype=np.uint8), (region("Same", (5, 5, 30, 15)),))
        latest = frame(20, np.full((80, 120, 3), 255, dtype=np.uint8), (region("Same", (5, 5, 30, 15)),))
        presentation = Presentation(slides=[Slide(
            1, 2.0, 4.0, builds=[SlideBuild([first, latest], "Same")],
        )])

        targets = select_visual_analysis_targets(
            presentation, source_reference="result:one", scope=VisualSelectionScope.ALL_SLIDES,
        )

        self.assertEqual((10, 20), tuple(target.frame_number for target in targets))

    def test_recommended_omits_text_dominant_but_all_slides_and_user_scope_include_it(self):
        text_frame = text_only_frame()
        presentation = Presentation(slides=[Slide(
            2, 2.0, 2.0, builds=[SlideBuild([text_frame], "text")],
        )])

        recommended = select_visual_analysis_targets(
            presentation, source_reference="result:one",
        )
        all_slides = select_visual_analysis_targets(
            presentation, source_reference="result:one", scope=VisualSelectionScope.ALL_SLIDES,
        )
        selected = select_visual_analysis_targets(
            presentation, source_reference="result:one", scope=VisualSelectionScope.USER_SELECTED,
            selected_slide_numbers=(2,),
        )

        self.assertEqual((), recommended)
        self.assertEqual((10,), tuple(target.frame_number for target in all_slides))
        self.assertEqual((10,), tuple(target.frame_number for target in selected))

    def test_explicit_frame_selection_bypasses_primary_selection(self):
        first = text_only_frame(10)
        latest = text_only_frame(20)
        presentation = Presentation(slides=[Slide(
            1, 2.0, 4.0, builds=[SlideBuild([first, latest], "text")],
        )])

        targets = select_visual_analysis_targets(
            presentation, source_reference="result:one", scope=VisualSelectionScope.USER_SELECTED,
            selected_frame_numbers=(10,),
        )

        self.assertEqual((10,), tuple(target.frame_number for target in targets))

    def test_target_order_is_slide_build_then_frame(self):
        slide_two = Slide(2, 0, 0, builds=[SlideBuild([pie_like_frame(30)], "chart")])
        slide_one = Slide(1, 0, 0, builds=[
            SlideBuild([diagram_like_frame(20)], "first"),
            SlideBuild([time_series_like_frame(25)], "second"),
        ])
        presentation = Presentation(slides=[slide_two, slide_one])

        targets = select_visual_analysis_targets(
            presentation, source_reference="result:one", scope=VisualSelectionScope.ALL_SLIDES,
        )

        keys = tuple((target.slide_number, target.build_index, target.frame_number) for target in targets)
        self.assertEqual(tuple(sorted(keys)), keys)

    def test_detection_and_selection_do_not_mutate_source_evidence(self):
        source = pie_like_frame()
        presentation = Presentation(
            metadata={"source": "preserved"},
            slides=[Slide(1, 0, 0, builds=[SlideBuild([source], "values")])],
            statistics={"slides": 1},
        )
        before = pickle.dumps(presentation)

        assess_visual_candidate(source)
        select_visual_analysis_targets(presentation, source_reference="result:one")

        self.assertEqual(before, pickle.dumps(presentation))

    def test_signals_are_revisioned_and_json_compatible(self):
        assessment = assess_visual_candidate(pie_like_frame())

        self.assertEqual(DETECTOR_REVISION, assessment.detector_revision)
        for value in assessment.signals:
            self.assertEqual(DETECTOR_REVISION, value.detector_revision)
            self.assertIsInstance(to_json_compatible(value.observed_values), dict)


if __name__ == "__main__":
    unittest.main()
