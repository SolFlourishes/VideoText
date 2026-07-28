"""Focused tests for shared successful-run completion summaries."""

import io
import queue
import sys
from contextlib import redirect_stdout
from pathlib import Path
import unittest
from unittest.mock import patch


sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import gui
import main
from models import Presentation, Slide
from processing_service import (
    ProcessingMode,
    ProcessingResult,
    format_processing_summary,
)


class ProcessingSummaryTests(unittest.TestCase):
    def result(
        self,
        mode=ProcessingMode.OCR_RESULTS,
        exported_paths=None,
        checkpoint=Path("source/cache/ocr_results.pkl"),
        frame_count=49,
    ):
        presentation = Presentation(slides=[
            Slide(slide_number=1, start_time=0.0, end_time=1.0),
            Slide(slide_number=2, start_time=1.0, end_time=2.0),
        ])
        return ProcessingResult(
            presentation=presentation,
            run_directory=Path("output/sample_replay"),
            exported_paths=(
                {
                    "markdown": "output/sample_replay/sample.md",
                    "excel": "output/sample_replay/sample.xlsx",
                }
                if exported_paths is None
                else exported_paths
            ),
            mode=mode,
            source_path="source/ocr_results.pkl",
            resolved_checkpoint_path=checkpoint,
            frame_count=frame_count,
            elapsed_seconds=65,
        )

    def test_full_video_summary_uses_friendly_mode_label(self):
        summary = format_processing_summary(
            self.result(mode=ProcessingMode.FULL_VIDEO, checkpoint=None)
        )

        self.assertIn("Mode: Full video", summary)
        self.assertIn("Candidate frames processed: 49", summary)

    def test_each_resume_mode_uses_a_friendly_label(self):
        expected = {
            ProcessingMode.CANDIDATE_FRAMES: "Candidate frames cache",
            ProcessingMode.OCR_RESULTS: "OCR results cache",
            ProcessingMode.READING_ORDER: "Reading-order cache",
        }

        for mode, label in expected.items():
            with self.subTest(mode=mode):
                self.assertIn(f"Mode: {label}", format_processing_summary(self.result(mode=mode)))

    def test_summary_includes_slide_count_elapsed_workspace_and_checkpoint(self):
        summary = format_processing_summary(self.result())

        self.assertIn("Slides created: 2", summary)
        self.assertIn("Elapsed time: 1m 05s", summary)
        self.assertIn(f"Output folder: {Path('output/sample_replay')}", summary)
        self.assertIn(
            f"Resolved checkpoint: {Path('source/cache/ocr_results.pkl')}",
            summary,
        )

    def test_summary_lists_only_exports_that_were_created(self):
        summary = format_processing_summary(self.result(exported_paths={
            "csv": "output/sample_replay/sample.csv",
        }))

        self.assertIn("- CSV: output/sample_replay/sample.csv", summary)
        self.assertNotIn("Markdown", summary)
        self.assertNotIn("Excel", summary)

    def test_missing_optional_values_are_omitted_cleanly(self):
        summary = format_processing_summary(self.result(
            checkpoint=None,
            frame_count=None,
        ))

        self.assertNotIn("Resolved checkpoint:", summary)
        self.assertNotIn("frames processed:", summary.lower())
        self.assertNotIn("None", summary)

    def test_cli_prints_one_shared_summary_without_saved_path_duplicates(self):
        result = self.result()
        captured = io.StringIO()

        with (
            patch.object(main, "select_cli_mode", return_value=ProcessingMode.READING_ORDER),
            patch.object(
                main,
                "_prompt_request",
                return_value=type("Request", (), {"formats": ["markdown", "excel"]})(),
            ),
            patch.object(main, "process_request", return_value=result),
            redirect_stdout(captured),
        ):
            main.main()

        output = captured.getvalue()
        self.assertEqual(output.count("Processing Complete"), 1)
        self.assertEqual(output.count("sample.md"), 1)
        self.assertNotIn("Saved Markdown", output)

    def test_gui_completion_queue_shows_summary_on_main_thread(self):
        app = object.__new__(gui.VideoTextApp)
        app.message_queue = queue.Queue()
        app.message_queue.put(("complete", self.result()))
        app.processing = True
        app.master = object()
        app._append_log = lambda _message: None
        app._finish_processing = lambda: setattr(app, "processing", False)
        app.after = lambda *_args: self.fail("No follow-up poll is needed")

        with patch.object(gui.VideoTextApp, "_show_completion_dialog") as dialog:
            gui.VideoTextApp._poll_worker_messages(app)

        dialog.assert_called_once_with(self.result())

    def test_gui_error_does_not_show_a_success_summary(self):
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


if __name__ == "__main__":
    unittest.main()
