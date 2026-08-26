"""Focused tests for the custom Tkinter completion dialog."""

import queue
import sys
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch


sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import gui
from models import Presentation
from processing_service import (
    ProcessingMode,
    ProcessingResult,
    format_processing_summary,
)


class CompletionDialogTests(unittest.TestCase):
    def result(
        self,
        checkpoint=Path("source/cache/ocr_results.pkl"),
        mode=ProcessingMode.OCR_RESULTS,
    ):
        return ProcessingResult(
            presentation=Presentation(),
            run_directory=Path("output/sample_replay"),
            exported_paths={
                "markdown": "D:/VideoText Output/sample_replay/sample.md",
                "csv": "D:/VideoText Output/sample_replay/sample.csv",
                "excel": "D:/VideoText Output/sample_replay/sample.xlsx",
            },
            mode=mode,
            source_path="D:/VideoText/source/cache/ocr_results.pkl",
            resolved_checkpoint_path=checkpoint,
            frame_count=49,
            elapsed_seconds=10,
            ocr_confidence_statistics=SimpleNamespace(
                region_count=2,
                mean=0.9,
                median=0.9,
                minimum=0.8,
                threshold=0.6,
                below_threshold_count=0,
                below_threshold_proportion=0.0,
            ),
        )

    def translation_result(self, provider_name="openai"):
        return SimpleNamespace(
            job=SimpleNamespace(
                provider_name=provider_name,
                target_languages=("es-419", "ko-KR"),
            ),
            export_result=SimpleNamespace(
                success_count=14,
                failure_count=0,
                paths={"excel": (Path("output/translations/review.xlsx"),)},
            ),
            review_recommended_count=1,
        )

    def assert_translation_section_order(self, text):
        headings = (
            "OCR Quality\n--------------------",
            "Translation\n--------------------",
            "Translation Outputs\n--------------------",
        )
        self.assertLess(text.index(headings[0]), text.index(headings[1]))
        self.assertLess(text.index(headings[1]), text.index(headings[2]))

    def test_dialog_text_uses_shared_summary_and_keeps_full_paths(self):
        result = self.result()
        text = gui._format_completion_dialog_text(format_processing_summary(result))

        self.assertIn("Mode: OCR results cache", text)
        self.assertIn("Resolved checkpoint:", text)
        self.assertIn("Run Summary\n--------------------", text)
        self.assertIn("OCR frames: 49", text)
        self.assertIn("Slides: 0", text)
        self.assertIn("Elapsed: 10 seconds", text)
        self.assertIn("Markdown\n    D:/VideoText Output/sample_replay/sample.md", text)
        self.assertIn("Excel\n    D:/VideoText Output/sample_replay/sample.xlsx", text)
        self.assertNotIn("- Markdown:", text)

    def test_optional_checkpoint_is_omitted_for_full_video(self):
        result = self.result(checkpoint=None)
        result = ProcessingResult(
            **{**result.__dict__, "mode": ProcessingMode.FULL_VIDEO}
        )

        text = gui._format_completion_dialog_text(format_processing_summary(result))

        self.assertNotIn("Resolved checkpoint:", text)

    def test_dialog_uses_read_only_selectable_text_and_custom_toplevel(self):
        source = Path(gui.__file__).read_text(encoding="utf-8")

        self.assertIn("tk.Toplevel(self.master)", source)
        self.assertIn('wrap="none"', source)
        self.assertIn('summary_text.configure(state="disabled")', source)
        self.assertIn("orient=\"vertical\"", source)
        self.assertIn("orient=\"horizontal\"", source)
        self.assertNotIn("messagebox.showinfo", source)

    def test_completion_arrives_through_main_thread_queue_and_enables_controls(self):
        app = object.__new__(gui.VideoTextApp)
        app.message_queue = queue.Queue()
        app.message_queue.put(("complete", self.result()))
        app.processing = True
        app._append_log = lambda _message: None
        app.after = lambda *_args: self.fail("No follow-up poll is needed")
        app._finish_processing = lambda: setattr(app, "processing", False)

        with patch.object(gui.VideoTextApp, "_show_completion_dialog") as dialog:
            gui.VideoTextApp._poll_worker_messages(app)

        dialog.assert_called_once()
        self.assertFalse(app.processing)

    def test_error_event_does_not_open_completion_dialog(self):
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

    def test_openai_full_video_uses_live_composition_with_translation_heading(self):
        text = gui._compose_completion_dialog_text(
            self.result(checkpoint=None, mode=ProcessingMode.FULL_VIDEO),
            self.translation_result("openai"),
        )

        self.assert_translation_section_order(text)
        self.assertIn("Provider: OpenAI Cloud", text)
        self.assertIn(
            "Target languages:\n    Spanish — Latin America\n    Korean — South Korea",
            text,
        )

    def test_openai_replay_uses_live_composition_with_translation_heading(self):
        text = gui._compose_completion_dialog_text(
            self.result(), self.translation_result("openai"),
        )

        self.assert_translation_section_order(text)
        self.assertIn("Mode: OCR results cache", text)
        self.assertIn("Provider: OpenAI Cloud", text)

    def test_local_completion_uses_live_composition_with_translation_heading(self):
        text = gui._compose_completion_dialog_text(
            self.result(), self.translation_result("local-ctranslate2"),
        )

        self.assert_translation_section_order(text)
        self.assertIn("Provider: Local Translation", text)

    def test_ocr_only_summary_has_no_translation_section(self):
        text = gui._compose_completion_dialog_text(self.result())

        self.assertNotIn("Translation\n--------------------", text)
        self.assertNotIn("Translation Outputs", text)


if __name__ == "__main__":
    unittest.main()
