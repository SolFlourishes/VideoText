"""Focused compatibility tests for the engine-neutral Paddle OCR adapter."""

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np


sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import ocr_engine
from config import OCR_LANGUAGE
from models import CandidateFrame, OCRResult


class FakePaddleOCR:
    instances = []
    prediction = []

    def __init__(self, **kwargs):
        self.kwargs = kwargs
        self.images = []
        type(self).instances.append(self)

    def predict(self, image):
        self.images.append(image)
        return type(self).prediction


def frame() -> CandidateFrame:
    return CandidateFrame(
        frame_number=1,
        timestamp=0.0,
        image=np.zeros((2, 2, 3), dtype=np.uint8),
        difference_score=0.0,
    )


class OCREngineContractTests(unittest.TestCase):
    def setUp(self):
        ocr_engine._ocr_engine = None
        FakePaddleOCR.instances = []
        FakePaddleOCR.prediction = []
        self.paddle_loader = patch.object(
            ocr_engine,
            "_load_paddle_ocr_class",
            return_value=FakePaddleOCR,
        )
        self.paddle_loader.start()
        self.addCleanup(self.paddle_loader.stop)
        self.addCleanup(setattr, ocr_engine, "_ocr_engine", None)

    def test_paddle_is_the_deterministic_default_registered_engine(self):
        names = ocr_engine.get_registered_ocr_engines()

        self.assertEqual(names, ("paddle",))
        self.assertEqual(ocr_engine.get_default_ocr_engine_name(), "paddle")
        self.assertIsInstance(names, tuple)
        self.assertEqual(names + ("other",), ("paddle", "other"))
        self.assertEqual(ocr_engine.get_registered_ocr_engines(), ("paddle",))

    def test_discovery_returns_paddle_deterministically_without_initializing_it(self):
        first = ocr_engine.discover_ocr_engines()
        second = ocr_engine.discover_ocr_engines()

        self.assertEqual(first, {"paddle": ocr_engine.PaddleOCREngine})
        self.assertEqual(second, first)
        self.assertIsNot(first, second)
        self.assertEqual(FakePaddleOCR.instances, [])

    def test_registry_is_seeded_from_discovery_and_isolated_from_returned_mapping(self):
        discovered = ocr_engine.discover_ocr_engines()
        self.assertEqual(ocr_engine._ENGINE_FACTORIES, discovered)
        discovered.pop("paddle")

        self.assertEqual(ocr_engine.get_registered_ocr_engines(), ("paddle",))
        self.assertIsInstance(ocr_engine.create_ocr_engine("paddle"), ocr_engine.PaddleOCREngine)

    def test_create_paddle_returns_an_uninitialized_engine_contract(self):
        adapter = ocr_engine.create_ocr_engine("paddle")

        self.assertIsInstance(adapter, ocr_engine.OCREngine)
        self.assertIsInstance(adapter, ocr_engine.PaddleOCREngine)
        self.assertEqual(FakePaddleOCR.instances, [])

    def test_unknown_engine_names_fail_with_available_names(self):
        with self.assertRaisesRegex(
            ValueError,
            r"Unknown OCR engine: unknown\. Available engines: paddle\.",
        ):
            ocr_engine.create_ocr_engine("unknown")

    def test_paddle_response_parsing_preserves_order_confidence_and_boxes(self):
        first_box = np.array([1, 2, 30, 40])
        second_box = np.array([50, 3, 80, 42])
        FakePaddleOCR.prediction = [{
            "rec_texts": ["first", "second"],
            "rec_scores": [0.6000001, 0.9876543],
            "rec_boxes": [first_box, second_box],
        }]

        regions = ocr_engine.PaddleOCREngine().recognize(np.zeros((1, 1, 3)))

        self.assertTrue(all(isinstance(region, OCRResult) for region in regions))
        self.assertEqual([region.text for region in regions], ["first", "second"])
        self.assertEqual([region.confidence for region in regions], [0.6000001, 0.9876543])
        self.assertIs(regions[0].bounding_box, first_box)
        self.assertIs(regions[1].bounding_box, second_box)

    def test_empty_prediction_and_empty_page_return_no_regions(self):
        adapter = ocr_engine.PaddleOCREngine()

        FakePaddleOCR.prediction = []
        self.assertEqual(adapter.recognize(np.zeros((1, 1, 3))), [])
        FakePaddleOCR.prediction = [{}]
        self.assertEqual(adapter.recognize(np.zeros((1, 1, 3))), [])

    def test_adapter_exposes_only_the_engine_neutral_recognize_contract(self):
        self.assertTrue(hasattr(ocr_engine.PaddleOCREngine(), "recognize"))
        self.assertFalse(hasattr(ocr_engine.PaddleOCREngine(), "predict"))

    def test_adapter_initialization_is_lazy_and_uses_current_paddle_settings(self):
        adapter = ocr_engine.PaddleOCREngine()
        self.assertEqual(FakePaddleOCR.instances, [])

        adapter.recognize(np.zeros((1, 1, 3)))

        self.assertEqual(len(FakePaddleOCR.instances), 1)
        self.assertEqual(FakePaddleOCR.instances[0].kwargs, {
            "use_textline_orientation": True,
            "lang": OCR_LANGUAGE,
        })

    def test_factory_initializes_once_and_reuses_the_process_singleton(self):
        first = ocr_engine.get_ocr_engine()
        second = ocr_engine.get_ocr_engine()

        self.assertIs(first, second)
        self.assertEqual(len(FakePaddleOCR.instances), 1)

    def test_explicit_registry_instances_do_not_replace_the_production_singleton(self):
        explicit = ocr_engine.create_ocr_engine("paddle")
        production = ocr_engine.get_ocr_engine()

        self.assertIsNot(explicit, production)
        self.assertEqual(len(FakePaddleOCR.instances), 1)

    def test_perform_ocr_uses_recognize_and_preserves_raw_working_references(self):
        source = frame()
        region = OCRResult("visible", 0.95, np.array([0, 0, 10, 10]))

        class ContractEngine:
            def __init__(self):
                self.images = []

            def recognize(self, image):
                self.images.append(image)
                return [region]

        engine = ContractEngine()
        with patch.object(ocr_engine, "get_ocr_engine", return_value=engine):
            ocr_engine.perform_ocr([source])

        self.assertEqual(engine.images, [source.image])
        self.assertIsNot(source.raw_ocr_results, source.ocr_results)
        self.assertIs(source.raw_ocr_results[0], region)
        self.assertIs(source.ocr_results[0], region)


if __name__ == "__main__":
    unittest.main()
