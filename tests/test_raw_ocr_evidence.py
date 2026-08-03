"""Focused regression tests for retained raw OCR evidence."""

import io
import pickle
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

import numpy as np


sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import ocr_engine
import processing_service
from cache_manager import load_cache
from models import CandidateFrame, OCRResult, Presentation, ensure_raw_ocr_results
from processing_service import ProcessingMode, ProcessingRequest, process_request
from reading_order import reconstruct_reading_order


def frame() -> CandidateFrame:
    return CandidateFrame(
        frame_number=1,
        timestamp=0.0,
        image=np.zeros((20, 40, 3), dtype=np.uint8),
        difference_score=0.0,
    )


def region(text: str, confidence: float, left: int) -> OCRResult:
    return OCRResult(text, confidence, np.array([left, 0, left + 20, 10]))


class FakeOCREngine:
    def recognize(self, _image):
        return [
            OCRResult("high", 0.95, np.array([0, 0, 20, 10])),
            OCRResult("low", 0.59, np.array([25, 0, 45, 10])),
        ]


class RawOCREvidenceTests(unittest.TestCase):
    def test_existing_candidate_frame_positional_constructor_still_works(self):
        source = CandidateFrame(
            1,
            0.0,
            np.zeros((20, 40, 3), dtype=np.uint8),
            0.0,
            [],
            [],
            [],
            False,
        )

        self.assertEqual(source.raw_ocr_results, [])

    def test_candidate_frame_raw_evidence_defaults_are_independent(self):
        first = frame()
        second = frame()

        first.raw_ocr_results.append(region("first", 0.9, 0))

        self.assertEqual(len(first.raw_ocr_results), 1)
        self.assertEqual(second.raw_ocr_results, [])

    def test_ocr_populates_raw_and_working_lists_with_same_regions(self):
        source = frame()

        with patch.object(ocr_engine, "get_ocr_engine", return_value=FakeOCREngine()):
            ocr_engine.perform_ocr([source])

        self.assertEqual([item.text for item in source.raw_ocr_results], ["high", "low"])
        self.assertEqual([item.text for item in source.ocr_results], ["high", "low"])
        self.assertIsNot(source.raw_ocr_results, source.ocr_results)
        self.assertIs(source.raw_ocr_results[0], source.ocr_results[0])

    def test_reading_order_filters_only_the_working_results(self):
        source = frame()
        high = region("visible", 0.95, 0)
        low = region("hidden", 0.59, 25)
        source.raw_ocr_results = [high, low]
        source.ocr_results = [high, low]

        reconstruct_reading_order([source])

        self.assertEqual([item.text for item in source.ocr_results], ["visible"])
        self.assertEqual([item.text for item in source.raw_ocr_results], ["visible", "hidden"])
        self.assertEqual([line.text for line in source.text_lines], ["visible"])

    def test_reading_order_has_no_temporary_console_dump(self):
        source = frame()
        source.ocr_results = [region("visible", 0.95, 0)]

        console = io.StringIO()
        with redirect_stdout(console):
            reconstruct_reading_order([source])

        self.assertEqual(console.getvalue(), "")
        self.assertEqual([line.text for line in source.text_lines], ["visible"])

    def test_legacy_frame_without_raw_evidence_is_normalized_safely(self):
        source = frame()
        source.ocr_results = [region("surviving", 0.95, 0)]
        del source.raw_ocr_results

        raw = ensure_raw_ocr_results(source)

        self.assertEqual([item.text for item in raw], ["surviving"])
        self.assertIsNot(raw, source.ocr_results)
        self.assertIs(raw[0], source.ocr_results[0])

    def test_legacy_reading_order_replay_uses_surviving_evidence_without_failure(self):
        source = frame()
        source.ocr_results = [region("surviving", 0.95, 0)]
        del source.raw_ocr_results

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            checkpoint = root / "prior" / "cache" / "reading_order.pkl"
            checkpoint.parent.mkdir(parents=True)
            with checkpoint.open("wb") as file:
                pickle.dump([source], file)

            request = ProcessingRequest(
                mode=ProcessingMode.READING_ORDER,
                source_path=str(checkpoint),
                output_directory=root / "output",
                formats=["markdown"],
            )
            with (
                patch.object(processing_service, "_create_presentation", return_value=Presentation()),
                patch.object(processing_service, "export_all", return_value={}),
            ):
                result = process_request(request)

            replay_frame = load_cache(result.run_directory / "cache" / "reading_order.pkl")[0]
            self.assertEqual([item.text for item in replay_frame.raw_ocr_results], ["surviving"])
            self.assertEqual([item.text for item in replay_frame.ocr_results], ["surviving"])


if __name__ == "__main__":
    unittest.main()
