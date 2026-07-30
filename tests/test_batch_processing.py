"""Focused tests for shared sequential VideoText batch processing."""

import sys
import tempfile
import builtins
from pathlib import Path
import unittest
from unittest.mock import patch


sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import batch_processing
import gui
import main
from batch_processing import (
    BatchItemResult,
    BatchProcessingResult,
    BatchProcessingRequest,
    normalize_video_paths,
    format_batch_summary,
    process_batch,
    videos_in_folder,
)
from menu import CliProcessingMode
from models import Presentation, Slide, TextParagraph, TextType
from processing_service import ProcessingMode, ProcessingProgress, ProcessingResult


class BatchProcessingTests(unittest.TestCase):
    def setUp(self):
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary_directory.cleanup)
        self.root = Path(self.temporary_directory.name)

    def processing_result(self, source_path: str) -> ProcessingResult:
        stem = Path(source_path).stem
        workspace = self.root / "output" / stem
        return ProcessingResult(
            presentation=Presentation(),
            run_directory=workspace,
            exported_paths={"markdown": str(workspace / f"{stem}.md")},
            mode=ProcessingMode.FULL_VIDEO,
            source_path=source_path,
            resolved_checkpoint_path=None,
            frame_count=3,
            elapsed_seconds=2,
        )

    def request(self, paths, progress_callback=None):
        return BatchProcessingRequest(
            source_paths=paths,
            output_directory=self.root / "output",
            formats=["markdown", "excel"],
            progress_callback=progress_callback,
        )

    def test_folder_selection_uses_supported_sorted_non_recursive_files(self):
        folder = self.root / "videos"
        folder.mkdir()
        for name in ("z.mov", "a.MP4", "notes.txt", "b.mkv"):
            (folder / name).touch()
        (folder / "nested").mkdir()
        (folder / "nested" / "inside.mp4").touch()

        self.assertEqual(
            [Path(path).name for path in videos_in_folder(folder)],
            ["a.MP4", "b.mkv", "z.mov"],
        )

    def test_duplicate_paths_preserve_first_occurrence_order(self):
        self.assertEqual(
            normalize_video_paths(["one.mp4", "two.mp4", "one.mp4", "two.mp4"]),
            ["one.mp4", "two.mp4"],
        )

    def test_empty_folder_reports_a_clear_error(self):
        folder = self.root / "empty"
        folder.mkdir()

        with self.assertRaisesRegex(ValueError, "No supported video files"):
            videos_in_folder(folder)

    def test_items_delegate_in_order_to_full_video_requests_with_shared_formats(self):
        paths = ["first.mp4", "second.mp4"]
        calls = []

        def process(request):
            calls.append(request)
            return self.processing_result(request.source_path)

        with patch.object(batch_processing, "process_request", side_effect=process):
            result = process_batch(self.request(paths))

        self.assertEqual([call.source_path for call in calls], paths)
        self.assertTrue(all(call.mode is ProcessingMode.FULL_VIDEO for call in calls))
        self.assertTrue(all(call.formats == ["markdown", "excel"] for call in calls))
        self.assertTrue(all(item.success for item in result.items))
        self.assertEqual(result.items[0].processing_result.run_directory, self.root / "output" / "first")

    def test_failure_is_recorded_and_next_video_continues(self):
        paths = ["first.mp4", "broken.mp4", "third.mp4"]

        def process(request):
            if request.source_path == "broken.mp4":
                raise ValueError("Unable to open video stream")
            return self.processing_result(request.source_path)

        with patch.object(batch_processing, "process_request", side_effect=process):
            result = process_batch(self.request(paths))

        self.assertEqual([item.success for item in result.items], [True, False, True])
        self.assertIsNone(result.items[1].processing_result)
        self.assertIn("Unable to open video stream", result.items[1].error_message)
        self.assertEqual(result.items[2].source_path, "third.mp4")

    def test_batch_log_is_incremental_and_contains_only_operational_details(self):
        paths = ["first.mp4", "broken.mp4"]

        def process(request):
            logs = list((self.root / "output").glob("VideoText_batch_*.log"))
            self.assertTrue(logs)
            if request.source_path == "broken.mp4":
                raise RuntimeError("bad stream")
            return self.processing_result(request.source_path)

        with patch.object(batch_processing, "process_request", side_effect=process):
            result = process_batch(self.request(paths))

        log_text = result.log_path.read_text(encoding="utf-8")
        self.assertIn("Status: Success", log_text)
        self.assertIn("Status: Failed", log_text)
        self.assertIn("Output workspace:", log_text)
        self.assertIn("Error: RuntimeError: bad stream", log_text)
        self.assertNotIn("extracted paragraph content", log_text)

    def test_batch_progress_wraps_shared_item_progress(self):
        events = []

        def process(request):
            request.progress_callback(ProcessingProgress(
                stage="ocr",
                message="Running OCR",
                current=1,
                total=2,
                elapsed_seconds=1,
                estimated_remaining_seconds=None,
            ))
            return self.processing_result(request.source_path)

        with patch.object(batch_processing, "process_request", side_effect=process):
            process_batch(self.request(["first.mp4"], events.append))

        self.assertEqual(events[0].current_item, 1)
        self.assertEqual(events[0].total_items, 1)
        self.assertEqual(events[0].filename, "first.mp4")
        self.assertIsNone(events[0].progress)
        self.assertEqual(events[1].progress.stage, "ocr")

    def test_cli_multiple_file_and_folder_requests_use_batch_service_inputs(self):
        with patch.object(
            builtins,
            "input",
            side_effect=["first.mp4", "second.mp4", "", str(self.root / "output"), "1,3"],
        ):
            files_request = main._prompt_batch_request(CliProcessingMode.BATCH_FILES)

        folder = self.root / "folder"
        folder.mkdir()
        (folder / "one.mp4").touch()
        with patch.object(
            builtins,
            "input",
            side_effect=[str(folder), str(self.root / "output"), "2"],
        ):
            folder_request = main._prompt_batch_request(CliProcessingMode.BATCH_FOLDER)

        self.assertEqual(files_request.source_paths, ["first.mp4", "second.mp4"])
        self.assertEqual(files_request.formats, ["markdown", "excel"])
        self.assertEqual([Path(path).name for path in folder_request.source_paths], ["one.mp4"])
        self.assertEqual(folder_request.formats, ["csv"])

    def test_batch_summary_and_gui_use_one_final_batch_dialog(self):
        successful = BatchItemResult(
            "first.mp4", True, self.processing_result("first.mp4"), None, 1,
        )
        failed = BatchItemResult(
            "broken.mp4", False, None, "ValueError: bad stream", 1,
        )
        result = BatchProcessingResult(
            [successful, failed], self.root / "output" / "batch.log", 2,
        )
        summary = format_batch_summary(result)
        gui_source = Path(gui.__file__).read_text(encoding="utf-8")

        self.assertIn("Batch Processing Complete", summary)
        self.assertIn("Completed: 1", summary)
        self.assertIn("Failed: 1", summary)
        self.assertIn("ValueError: bad stream", summary)
        self.assertIn("def _show_batch_completion_dialog", gui_source)
        batch_handler = gui_source.split('elif message_type == "batch_complete"', maxsplit=1)[1]
        batch_handler = batch_handler.split('elif message_type == "error"', maxsplit=1)[0]
        self.assertIn("_show_batch_completion_dialog(payload)", batch_handler)
        self.assertNotIn("_show_completion_dialog(payload)", batch_handler)

    def test_consolidated_excel_uses_one_batch_workbook_and_skips_per_video_excel(self):
        paths = ["first.mp4", "second.mp4"]

        def process(request):
            self.assertEqual(request.formats, ["markdown"])
            result = self.processing_result(request.source_path)
            return ProcessingResult(
                presentation=Presentation(slides=[Slide(
                    slide_number=1,
                    start_time=0,
                    end_time=1,
                    paragraphs=[TextParagraph("Text", text_type=TextType.BODY)],
                )]),
                run_directory=result.run_directory,
                exported_paths=result.exported_paths,
                mode=result.mode,
                source_path=result.source_path,
                resolved_checkpoint_path=None,
                frame_count=1,
                elapsed_seconds=1,
            )

        request = BatchProcessingRequest(
            source_paths=paths,
            output_directory=self.root / "output",
            formats=["markdown", "excel"],
            consolidated_excel=True,
        )
        with patch.object(batch_processing, "process_request", side_effect=process):
            result = process_batch(request)

        self.assertIsNotNone(result.consolidated_excel_path)
        self.assertTrue(Path(result.consolidated_excel_path).is_file())
        self.assertIn("Consolidated Excel:", format_batch_summary(result))

    def test_all_failed_consolidated_batch_leaves_no_empty_workbook(self):
        request = BatchProcessingRequest(
            source_paths=["broken.mp4"],
            output_directory=self.root / "output",
            formats=["excel"],
            consolidated_excel=True,
        )
        with patch.object(batch_processing, "process_request", side_effect=ValueError("bad video")):
            result = process_batch(request)

        self.assertIsNone(result.consolidated_excel_path)
        self.assertFalse((self.root / "output" / "Batch VideoText Export.xlsx").exists())

    def test_gui_exposes_batch_excel_choice_only_with_excel_selection(self):
        source = Path(gui.__file__).read_text(encoding="utf-8")

        self.assertIn("self.batch_excel_frame", source)
        self.assertIn("One workbook per video", source)
        self.assertIn("One workbook for the entire batch", source)
        self.assertIn("_update_batch_excel_options", source)
        self.assertIn("consolidated_excel=self.batch_excel_consolidated.get()", source)


if __name__ == "__main__":
    unittest.main()
