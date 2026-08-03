"""Focused tests for descriptive raw-OCR confidence statistics."""

from dataclasses import FrozenInstanceError
from pathlib import Path
import sys
import unittest

import numpy as np


sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from config import MIN_CONFIDENCE
from models import CandidateFrame, OCRResult
from ocr_confidence_stats import (
    DocumentOCRConfidenceStats,
    OCRConfidenceStats,
    calculate_document_ocr_confidence_stats,
    calculate_ocr_confidence_stats,
)


def frame(raw_confidences, working_confidences=None):
    candidate = CandidateFrame(
        frame_number=1,
        timestamp=0.0,
        image=np.zeros((20, 40, 3), dtype=np.uint8),
        difference_score=0.0,
    )
    candidate.raw_ocr_results = [
        OCRResult(f"raw-{index}", confidence, np.array([index, 0, index + 1, 1]))
        for index, confidence in enumerate(raw_confidences)
    ]
    active = raw_confidences if working_confidences is None else working_confidences
    candidate.ocr_results = [
        OCRResult(f"working-{index}", confidence, np.array([index, 2, index + 1, 3]))
        for index, confidence in enumerate(active)
    ]
    return candidate


class OCRConfidenceStatsTests(unittest.TestCase):
    def test_empty_raw_evidence_has_explicit_zero_and_none_values(self):
        stats = calculate_ocr_confidence_stats(frame([]))

        self.assertEqual(stats.region_count, 0)
        self.assertIsNone(stats.minimum)
        self.assertIsNone(stats.maximum)
        self.assertIsNone(stats.mean)
        self.assertIsNone(stats.median)
        self.assertEqual(stats.below_threshold_count, 0)
        self.assertEqual(stats.below_threshold_proportion, 0.0)

    def test_one_region(self):
        stats = calculate_ocr_confidence_stats(frame([0.75]))

        self.assertEqual(stats.region_count, 1)
        self.assertEqual((stats.minimum, stats.maximum, stats.mean, stats.median), (0.75, 0.75, 0.75, 0.75))
        self.assertEqual(stats.below_threshold_count, 0)

    def test_odd_and_even_counts_use_standard_median(self):
        odd = calculate_ocr_confidence_stats(frame([0.9, 0.2, 0.6]))
        even = calculate_ocr_confidence_stats(frame([0.9, 0.2, 0.6, 0.8]))

        self.assertEqual(odd.median, 0.6)
        self.assertEqual(even.median, 0.7)
        self.assertAlmostEqual(odd.mean, 1.7 / 3)
        self.assertAlmostEqual(even.mean, 0.625)

    def test_threshold_comparison_is_strict_and_uses_authoritative_constant(self):
        stats = calculate_ocr_confidence_stats(frame([0.59, 0.60, 0.61]))

        self.assertEqual(stats.threshold, MIN_CONFIDENCE)
        self.assertEqual(stats.below_threshold_count, 1)
        self.assertAlmostEqual(stats.below_threshold_proportion, 1 / 3)

    def test_all_above_and_all_below_threshold(self):
        above = calculate_ocr_confidence_stats(frame([0.60, 0.70, 1.0]))
        below = calculate_ocr_confidence_stats(frame([0.0, 0.20, 0.59]))

        self.assertEqual(above.below_threshold_count, 0)
        self.assertEqual(above.below_threshold_proportion, 0.0)
        self.assertEqual(below.below_threshold_count, 3)
        self.assertEqual(below.below_threshold_proportion, 1.0)

    def test_raw_evidence_is_used_not_filtered_working_results(self):
        stats = calculate_ocr_confidence_stats(
            frame([0.30, 0.90], working_confidences=[0.90])
        )

        self.assertEqual(stats.region_count, 2)
        self.assertEqual(stats.below_threshold_count, 1)
        self.assertAlmostEqual(stats.mean, 0.60)

    def test_input_order_and_objects_are_not_mutated(self):
        candidate = frame([0.90, 0.20, 0.70])
        raw_order = list(candidate.raw_ocr_results)
        working_order = list(candidate.ocr_results)
        raw_values = [item.confidence for item in candidate.raw_ocr_results]
        raw_texts = [item.text for item in candidate.raw_ocr_results]
        raw_boxes = [item.bounding_box.copy() for item in candidate.raw_ocr_results]

        first = calculate_ocr_confidence_stats(candidate)
        candidate.raw_ocr_results.reverse()
        second = calculate_ocr_confidence_stats(candidate)

        self.assertEqual(first, second)
        candidate.raw_ocr_results.reverse()
        self.assertEqual(
            [id(item) for item in candidate.raw_ocr_results],
            [id(item) for item in raw_order],
        )
        self.assertEqual(
            [id(item) for item in candidate.ocr_results],
            [id(item) for item in working_order],
        )
        self.assertEqual([item.confidence for item in candidate.raw_ocr_results], raw_values)
        self.assertEqual([item.text for item in candidate.raw_ocr_results], raw_texts)
        for item, original_box in zip(candidate.raw_ocr_results, raw_boxes):
            np.testing.assert_array_equal(item.bounding_box, original_box)

    def test_statistics_are_immutable_and_independent(self):
        first = calculate_ocr_confidence_stats(frame([0.4]))
        second = calculate_ocr_confidence_stats(frame([0.8]))

        self.assertIsInstance(first, OCRConfidenceStats)
        self.assertIsNot(first, second)
        self.assertNotEqual(first, second)
        with self.assertRaises(FrozenInstanceError):
            first.region_count = 9


class DocumentOCRConfidenceStatsTests(unittest.TestCase):
    def test_no_frames_has_explicit_empty_document_values(self):
        stats = calculate_document_ocr_confidence_stats([])

        self.assertEqual((stats.frame_count, stats.frames_with_ocr, stats.region_count), (0, 0, 0))
        self.assertEqual(stats.below_threshold_proportion, 0.0)
        self.assertIsNone(stats.minimum)
        self.assertIsNone(stats.maximum)
        self.assertIsNone(stats.mean)
        self.assertIsNone(stats.median)

    def test_empty_frames_are_counted_but_do_not_create_regions(self):
        stats = calculate_document_ocr_confidence_stats([frame([]), frame([])])

        self.assertEqual((stats.frame_count, stats.frames_with_ocr, stats.region_count), (2, 0, 0))
        self.assertEqual(stats.below_threshold_count, 0)
        self.assertEqual(stats.below_threshold_proportion, 0.0)

    def test_one_and_multiple_populated_frames_use_all_regions(self):
        one = calculate_document_ocr_confidence_stats([frame([0.75])])
        multiple = calculate_document_ocr_confidence_stats([
            frame([0.20, 0.90]),
            frame([]),
            frame([0.60, 0.80]),
        ])

        self.assertEqual((one.frame_count, one.frames_with_ocr, one.region_count), (1, 1, 1))
        self.assertEqual(one.mean, 0.75)
        self.assertEqual((multiple.frame_count, multiple.frames_with_ocr, multiple.region_count), (3, 2, 4))
        self.assertEqual((multiple.minimum, multiple.maximum, multiple.median), (0.20, 0.90, 0.70))
        self.assertAlmostEqual(multiple.mean, 0.625)

    def test_raw_evidence_and_strict_threshold_are_used(self):
        stats = calculate_document_ocr_confidence_stats([
            frame([0.59, 0.60, 0.90], working_confidences=[0.90]),
        ])

        self.assertEqual(stats.threshold, MIN_CONFIDENCE)
        self.assertEqual(stats.region_count, 3)
        self.assertEqual(stats.below_threshold_count, 1)
        self.assertAlmostEqual(stats.below_threshold_proportion, 1 / 3)

    def test_input_order_does_not_affect_results_or_mutate_frames(self):
        first = frame([0.90, 0.20])
        second = frame([0.70])
        frames = [first, second]
        raw_orders = [[id(item) for item in candidate.raw_ocr_results] for candidate in frames]
        working_orders = [[id(item) for item in candidate.ocr_results] for candidate in frames]
        boxes = [
            [item.bounding_box.copy() for item in candidate.raw_ocr_results]
            for candidate in frames
        ]

        forward = calculate_document_ocr_confidence_stats(frames)
        reverse = calculate_document_ocr_confidence_stats(list(reversed(frames)))

        self.assertEqual(forward, reverse)
        self.assertEqual(
            [[id(item) for item in candidate.raw_ocr_results] for candidate in frames],
            raw_orders,
        )
        self.assertEqual(
            [[id(item) for item in candidate.ocr_results] for candidate in frames],
            working_orders,
        )
        for candidate, original_boxes in zip(frames, boxes):
            for item, original_box in zip(candidate.raw_ocr_results, original_boxes):
                np.testing.assert_array_equal(item.bounding_box, original_box)

    def test_document_statistics_are_immutable_and_independent(self):
        first = calculate_document_ocr_confidence_stats([frame([0.4])])
        second = calculate_document_ocr_confidence_stats([frame([0.8])])

        self.assertIsInstance(first, DocumentOCRConfidenceStats)
        self.assertIsNot(first, second)
        with self.assertRaises(FrozenInstanceError):
            first.frame_count = 9


if __name__ == "__main__":
    unittest.main()
