"""Focused presentation-only GUI coverage for OCR quality completion details."""

import queue
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np


sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import gui
import processing_service
from models import CandidateFrame, OCRResult, Presentation
from ocr_confidence_stats import calculate_document_ocr_confidence_stats
from processing_service import ProcessingMode, ProcessingResult


def frame(raw_confidences, working_confidences=None) -> CandidateFrame:
    candidate = CandidateFrame(
        frame_number=1,
        timestamp=0.0,
        image=np.zeros((2, 2, 3), dtype=np.uint8),
        difference_score=0.0,
    )
    candidate.raw_ocr_results = [
        OCRResult(f"raw-{index}", confidence, np.array([index, 0, index + 1, 1]))
        for index, confidence in enumerate(raw_confidences)
    ]
    active = raw_confidences if working_confidences is None else working_confidences
    candidate.ocr_results = [
        OCRResult(f"working-{index}", confidence, np.array([index, 1, index + 1, 2]))
        for index, confidence in enumerate(active)
    ]
    return candidate


def result(statistics=None) -> ProcessingResult:
    return ProcessingResult(
        presentation=Presentation(),
        run_directory=Path("output/example"),
        exported_paths={},
        mode=ProcessingMode.FULL_VIDEO,
        source_path="source.mp4",
        resolved_checkpoint_path=None,
        frame_count=1,
        elapsed_seconds=1.0,
        ocr_confidence_statistics=statistics,
    )


class GUIOCRQualitySummaryTests(unittest.TestCase):
    def test_populated_summary_formats_all_requested_statistics(self):
        statistics = calculate_document_ocr_confidence_stats([
            frame([0.528, 0.942, 0.914]),
        ])

        summary = gui._format_ocr_quality_section(statistics)

        self.assertIn("OCR Quality", summary)
        self.assertIn("OCR regions: 3", summary)
        self.assertIn("Mean confidence: 79.5%", summary)
        self.assertIn("Median confidence: 91.4%", summary)
        self.assertIn("Minimum confidence: 52.8%", summary)
        self.assertIn("Below 60%: 1 regions (33.3%)", summary)
        self.assertIn("Active threshold: 60.0%", summary)

    def test_empty_evidence_has_an_explicit_unavailable_summary(self):
        summary = gui._format_ocr_quality_section(
            calculate_document_ocr_confidence_stats([frame([])])
        )

        self.assertIn("OCR regions: 0", summary)
        self.assertIn("Confidence statistics unavailable", summary)
        self.assertIn("Active threshold: 60.0%", summary)
        self.assertNotIn("Mean confidence", summary)

    def test_raw_evidence_is_used_without_mutating_frames(self):
        candidate = frame([0.59, 0.90], working_confidences=[0.90])
        raw_before = list(candidate.raw_ocr_results)
        working_before = list(candidate.ocr_results)

        summary = gui._format_ocr_quality_section(
            calculate_document_ocr_confidence_stats([candidate])
        )

        self.assertIn("OCR regions: 2", summary)
        self.assertIn("Below 60%: 1 regions (50.0%)", summary)
        self.assertEqual(candidate.raw_ocr_results, raw_before)
        self.assertEqual(candidate.ocr_results, working_before)

    def test_completion_sections_are_result_specific_and_do_not_retain_prior_runs(self):
        populated = gui._format_ocr_quality_section(
            calculate_document_ocr_confidence_stats([frame([0.90])])
        )
        empty = gui._format_ocr_quality_section(
            calculate_document_ocr_confidence_stats([frame([])])
        )

        self.assertIn("Mean confidence: 90.0%", populated)
        self.assertNotIn("Mean confidence", empty)
        self.assertIn("Confidence statistics unavailable", empty)

    def test_failure_does_not_render_a_stale_quality_summary(self):
        app = object.__new__(gui.VideoTextApp)
        app.message_queue = queue.Queue()
        app.message_queue.put(("error", "failure"))
        app.processing = True
        app._set_status = lambda _message: None
        app._finish_processing = lambda: setattr(app, "processing", False)
        app.after = lambda *_args: self.fail("No follow-up poll is needed")

        with patch.object(gui.VideoTextApp, "_show_completion_dialog") as dialog:
            gui.VideoTextApp._poll_worker_messages(app)

        dialog.assert_not_called()

    def test_processing_service_calculates_once_and_returns_statistics(self):
        candidate_frames = [frame([0.90])]
        request = type("Request", (), {
            "formats": ["markdown"],
            "mode": ProcessingMode.FULL_VIDEO,
            "source_path": "source.mp4",
        })()
        reporter = type("Reporter", (), {
            "stage": lambda *_args: None,
            "item": lambda *_args: None,
            "complete": lambda *_args: None,
            "total_elapsed_seconds": 1.0,
        })()

        with (
            patch.object(processing_service, "_create_presentation", return_value=Presentation()),
            patch.object(processing_service, "export_all", return_value={}) as exporter,
            patch.object(
                processing_service,
                "calculate_document_ocr_confidence_stats",
                wraps=calculate_document_ocr_confidence_stats,
            ) as calculate,
        ):
            completed = processing_service._finish_run(
                candidate_frames,
                request,
                Path("output/example"),
                "example",
                {},
                reporter,
            )

        self.assertEqual(completed.ocr_confidence_statistics.region_count, 1)
        calculate.assert_called_once_with(candidate_frames)
        self.assertIs(
            exporter.call_args.kwargs["ocr_confidence_statistics"],
            completed.ocr_confidence_statistics,
        )


if __name__ == "__main__":
    unittest.main()
