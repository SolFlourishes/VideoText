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

    def test_predict_compatibility_returns_the_unparsed_paddle_response(self):
        prediction = [{"rec_texts": ["legacy"]}]
        FakePaddleOCR.prediction = prediction

        self.assertIs(ocr_engine.get_ocr_engine().predict(np.zeros((1, 1, 3))), prediction)

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
