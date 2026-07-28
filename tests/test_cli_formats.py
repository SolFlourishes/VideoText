"""Focused tests for CLI export-format selection and submission."""

import builtins
import io
import pickle
import sys
import tempfile
from contextlib import redirect_stdout
from pathlib import Path
import unittest
from unittest.mock import patch


sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import gui
import main
from processing_service import ProcessingMode, process_request
from models import Presentation


class CliFormatTests(unittest.TestCase):
    def test_markdown_selection_normalizes_to_markdown(self):
        self.assertEqual(main.normalize_export_formats("1"), ["markdown"])

    def test_csv_selection_normalizes_to_csv(self):
        self.assertEqual(main.normalize_export_formats("2"), ["csv"])

    def test_excel_selection_normalizes_to_excel(self):
        self.assertEqual(main.normalize_export_formats("3"), ["excel"])

    def test_all_selections_normalize_to_all_exporters(self):
        self.assertEqual(
            main.normalize_export_formats("1, 2, 3"),
            ["markdown", "csv", "excel"],
        )

    def test_excel_selection_produces_xlsx_path(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            checkpoint = root / "sample" / "cache" / "reading_order.pkl"
            checkpoint.parent.mkdir(parents=True)
            with checkpoint.open("wb") as checkpoint_file:
                pickle.dump([], checkpoint_file)

            with (
                patch.object(main, "select_processing_mode", return_value=ProcessingMode.READING_ORDER),
                patch.object(
                    builtins,
                    "input",
                    side_effect=[str(checkpoint), str(root / "output"), "3"],
                ),
            ):
                request = main._prompt_request()

            result = process_request(request)

            self.assertEqual(request.formats, ["excel"])
            self.assertEqual(set(result.exported_paths), {"excel"})
            self.assertEqual(Path(result.exported_paths["excel"]).suffix, ".xlsx")
            self.assertTrue(Path(result.exported_paths["excel"]).is_file())

    def test_full_and_resume_requests_share_format_normalization(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            video = root / "video.mp4"
            video.touch()
            checkpoint = root / "sample" / "cache" / "ocr_results.pkl"
            checkpoint.parent.mkdir(parents=True)
            checkpoint.write_bytes(b"placeholder")

            with (
                patch.object(main, "select_processing_mode", return_value=ProcessingMode.FULL_VIDEO),
                patch.object(
                    builtins,
                    "input",
                    side_effect=[str(video), str(root / "output"), "Markdown, EXCEL"],
                ),
            ):
                full_request = main._prompt_request()

            with (
                patch.object(main, "select_processing_mode", return_value=ProcessingMode.OCR_RESULTS),
                patch.object(
                    builtins,
                    "input",
                    side_effect=[str(checkpoint), str(root / "output"), "Markdown, EXCEL"],
                ),
            ):
                resume_request = main._prompt_request()

            self.assertEqual(full_request.formats, ["markdown", "excel"])
            self.assertEqual(resume_request.formats, full_request.formats)

    def test_main_confirms_the_final_formats_before_processing(self):
        captured = io.StringIO()

        with (
            patch.object(main, "select_cli_mode", return_value=ProcessingMode.READING_ORDER),
            patch.object(
                main,
                "_prompt_request",
                return_value=main.ProcessingRequest(
                    mode=ProcessingMode.READING_ORDER,
                    source_path="checkpoint.pkl",
                    output_directory=Path("output"),
                    formats=["markdown", "csv", "excel"],
                ),
            ),
            patch.object(main, "process_request") as process,
            redirect_stdout(captured),
        ):
            process.return_value = main.ProcessingResult(
                presentation=Presentation(),
                run_directory=Path("output/sample_replay"),
                exported_paths={},
                mode=ProcessingMode.READING_ORDER,
                source_path="checkpoint.pkl",
                resolved_checkpoint_path=Path("checkpoint.pkl"),
                frame_count=0,
                elapsed_seconds=0,
            )
            main.main()

        self.assertIn("Selected formats: markdown, csv, excel", captured.getvalue())

    def test_gui_export_selection_behavior_is_unchanged(self):
        gui_source = Path(gui.__file__).read_text(encoding="utf-8")
        self.assertIn('"excel": tk.BooleanVar(value=True)', gui_source)
        self.assertIn("process_request(request)", gui_source)


if __name__ == "__main__":
    unittest.main()
