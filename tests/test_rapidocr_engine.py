"""Focused feasibility tests for the unregistered RapidOCR adapter."""

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np


sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from ocr_engine import OCREngine
import ocr_engine
from ocr_adapter_certification import (
    assert_canonical_results,
    assert_equivalent_results,
)
import rapidocr_engine


class FakeRapidOCROutput:
    def __init__(self, boxes=(), txts=(), scores=()):
        self.boxes = boxes
        self.txts = txts
        self.scores = scores


class FakeRapidOCR:
    instances = []
    output = None

    def __init__(self):
        self.images = []
        type(self).instances.append(self)

    def __call__(self, image):
        self.images.append(image)
        return type(self).output


class RapidOCREngineTests(unittest.TestCase):
    def setUp(self):
        FakeRapidOCR.instances = []
        FakeRapidOCR.output = None
        self.loader = patch.object(
            rapidocr_engine,
            "_load_rapid_ocr_class",
            return_value=FakeRapidOCR,
        )
        self.loader.start()
        self.addCleanup(self.loader.stop)

    def test_rapidocr_remains_outside_production_discovery_and_registry(self):
        self.assertNotIn("rapid", ocr_engine.discover_ocr_engines())
        self.assertNotIn("rapid", ocr_engine.get_registered_ocr_engines())
        self.assertEqual(ocr_engine.get_default_ocr_engine_name(), "paddle")

    def test_adapter_is_lazy_and_structurally_satisfies_the_contract(self):
        adapter = rapidocr_engine.RapidOCREngine()

        self.assertIsInstance(adapter, OCREngine)
        self.assertEqual(FakeRapidOCR.instances, [])

        adapter.recognize(np.zeros((1, 1, 3), dtype=np.uint8))

        self.assertEqual(len(FakeRapidOCR.instances), 1)

    def test_recognize_preserves_region_order_text_and_confidence(self):
        first_quad = np.array(((2, 3), (10, 2), (11, 8), (1, 9)))
        second_quad = np.array(((20, 5), (30, 5), (30, 15), (20, 15)))
        FakeRapidOCR.output = FakeRapidOCROutput(
            boxes=(first_quad, second_quad),
            txts=("first", "second"),
            scores=(0.6000001, 0.9876543),
        )

        regions = rapidocr_engine.RapidOCREngine().recognize(
            np.zeros((1, 1, 3), dtype=np.uint8),
        )

        self.assertEqual([region.text for region in regions], ["first", "second"])
        self.assertEqual(
            [region.confidence for region in regions],
            [0.6000001, 0.9876543],
        )
        np.testing.assert_array_equal(regions[0].bounding_box, [1, 2, 11, 9])
        np.testing.assert_array_equal(regions[1].bounding_box, [20, 5, 30, 15])
        assert_canonical_results(self, regions)

    def test_empty_and_missing_output_return_no_regions(self):
        adapter = rapidocr_engine.RapidOCREngine()

        self.assertEqual(adapter.recognize(np.zeros((1, 1, 3))), [])
        FakeRapidOCR.output = FakeRapidOCROutput()
        self.assertEqual(adapter.recognize(np.zeros((1, 1, 3))), [])

    def test_inconsistent_result_collections_fail_without_dropping_regions(self):
        FakeRapidOCR.output = FakeRapidOCROutput(
            boxes=(np.zeros((4, 2)),),
            txts=("text", "extra"),
            scores=(0.9,),
        )

        with self.assertRaisesRegex(ValueError, "inconsistent"):
            rapidocr_engine.RapidOCREngine().recognize(np.zeros((1, 1, 3)))

    def test_non_quadrilateral_box_fails_clearly(self):
        FakeRapidOCR.output = FakeRapidOCROutput(
            boxes=(np.zeros((4,)),),
            txts=("text",),
            scores=(0.9,),
        )

        with self.assertRaisesRegex(ValueError, "four-point quadrilateral"):
            rapidocr_engine.RapidOCREngine().recognize(np.zeros((1, 1, 3)))

    def test_non_finite_confidence_is_rejected_without_fabrication(self):
        FakeRapidOCR.output = FakeRapidOCROutput(
            boxes=(np.zeros((4, 2)),),
            txts=("text",),
            scores=(float("inf"),),
        )

        with self.assertRaisesRegex(ValueError, "non-finite"):
            rapidocr_engine.RapidOCREngine().recognize(np.zeros((1, 1, 3)))

    def test_repeated_calls_are_deterministic_independent_and_do_not_mutate_image(self):
        image = np.zeros((2, 2, 3), dtype=np.uint8)
        original = image.copy()
        FakeRapidOCR.output = FakeRapidOCROutput(
            boxes=(np.array(((0, 0), (2, 0), (2, 2), (0, 2))),),
            txts=("same",),
            scores=(0.75,),
        )
        adapter = rapidocr_engine.RapidOCREngine()

        first = adapter.recognize(image)
        second = adapter.recognize(image)

        self.assertIsNot(first, second)
        self.assertIsNot(first[0], second[0])
        assert_equivalent_results(self, first, second)
        np.testing.assert_array_equal(image, original)
        self.assertEqual(len(FakeRapidOCR.instances), 1)
        assert_canonical_results(self, first)


if __name__ == "__main__":
    unittest.main()
