"""Focused deterministic geometry tests for OCR line reconstruction."""

from pathlib import Path
import sys
import unittest

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from models import OCRResult
from text_reconstruction import reconstruct_lines, reconstruct_lines_with_metadata


def region(text, box, confidence=0.9):
    return OCRResult(text, confidence, np.array(box))


class TextReconstructionTests(unittest.TestCase):
    def test_same_line_uses_geometry_not_source_order(self):
        lines = reconstruct_lines([
            region("feedback", [1380, 764, 1709, 812]),
            region("Evidence: I've never received_poor", [0, 763, 1342, 816]),
        ])
        self.assertEqual([line.text for line in lines], ["Evidence: I've never received_poor feedback"])

    def test_sample2_overlapping_lines_and_duplicate_suffix(self):
        lines, metadata = reconstruct_lines_with_metadata([
            region("Evidence: I've never received_poor", [0, 763, 1342, 816]),
            region("feedback", [1380, 764, 1709, 812]),
            region("Erom my boss. I am able to help", [0, 797, 1228, 871]),
            region(" my", [1197, 811, 1344, 867]),
        ])
        self.assertEqual([line.text for line in lines], [
            "Evidence: I've never received_poor feedback",
            "Erom my boss. I am able to help my",
        ])
        self.assertFalse(metadata[3].suppressed)

    def test_edge_aware_duplicate_suppression_preserves_interior_token(self):
        _, interior_metadata = reconstruct_lines_with_metadata([
            region("Erom my boss. I am able to help", [0, 797, 1228, 871]),
            region("my", [1197, 811, 1344, 867]),
        ])
        _, suffix_metadata = reconstruct_lines_with_metadata([
            region("I am able to help my", [0, 797, 1228, 871]),
            region("my", [1197, 811, 1344, 867]),
        ])
        _, prefix_metadata = reconstruct_lines_with_metadata([
            region("my customers resolve", [100, 797, 1228, 871]),
            region("my", [0, 811, 180, 867]),
        ])

        self.assertFalse(interior_metadata[1].suppressed)
        self.assertTrue(suffix_metadata[1].suppressed)
        self.assertTrue(prefix_metadata[1].suppressed)

    def test_distinct_or_non_overlapping_text_is_preserved(self):
        lines = reconstruct_lines([
            region("alpha", [0, 0, 100, 30]),
            region("beta", [70, 0, 140, 30]),
            region("alpha", [200, 0, 280, 30]),
        ])
        self.assertEqual(lines[0].text, "alpha beta alpha")

    def test_punctuation_unicode_empty_and_single_region(self):
        self.assertEqual(reconstruct_lines([]), [])
        self.assertEqual(reconstruct_lines([region("café", [0, 0, 50, 20])])[0].text, "café")
        self.assertEqual(reconstruct_lines([region("Hello", [0, 0, 50, 20]), region(", world", [51, 0, 100, 20])])[0].text, "Hello, world")

    def test_deterministic_output_does_not_mutate_source(self):
        regions = [region("right", [50, 0, 100, 20]), region("left", [0, 0, 40, 20])]
        original = regions[0].bounding_box.copy()
        first = [line.text for line in reconstruct_lines(regions)]
        second = [line.text for line in reconstruct_lines(regions)]
        self.assertEqual(first, second)
        np.testing.assert_array_equal(regions[0].bounding_box, original)


if __name__ == "__main__":
    unittest.main()
