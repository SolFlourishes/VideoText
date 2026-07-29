"""Focused tests for shared full and resumed VideoText processing."""

import inspect
from dataclasses import replace
import pickle
import sys
import tempfile
from pathlib import Path
import unittest
from unittest.mock import MagicMock, patch


sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import gui
import main
import processing_service
from models import Presentation
from processing_service import (
    CheckpointLoadError,
    CheckpointValidationError,
    ProcessingMode,
    ProcessingRequest,
    process_request,
    resolve_checkpoint_path,
)


class ProcessingServiceTests(unittest.TestCase):
    def setUp(self):
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary_directory.cleanup)
        self.root = Path(self.temporary_directory.name)
        self.output_root = self.root / "output"

    def checkpoint(self, name: str, data=None) -> Path:
        checkpoint_path = self.root / "sample" / "cache" / name
        checkpoint_path.parent.mkdir(parents=True)
        with checkpoint_path.open("wb") as checkpoint_file:
            pickle.dump([] if data is None else data, checkpoint_file)
        return checkpoint_path

    def request(self, mode: ProcessingMode, source: Path) -> ProcessingRequest:
        return ProcessingRequest(
            mode=mode,
            source_path=str(source),
            output_directory=self.output_root,
            formats=["markdown"],
        )

    def resume_patches(self):
        return (
            patch.object(processing_service, "perform_ocr", side_effect=lambda frames, **_: frames),
            patch.object(
                processing_service,
                "reconstruct_reading_order",
                side_effect=lambda frames, **_: frames,
            ),
            patch.object(
                processing_service,
                "export_all",
                return_value={"markdown": "saved.md"},
            ),
            patch.object(
                processing_service,
                "_create_presentation",
                return_value=Presentation(),
            ),
        )

    def test_reading_order_resume_skips_earlier_stages(self):
        checkpoint = self.checkpoint("reading_order.pkl")
        ocr, reading_order, exporter, create_presentation = self.resume_patches()
        messages = []

        with (
            ocr as perform_ocr,
            reading_order as reconstruct,
            exporter,
            create_presentation,
            patch.object(processing_service, "open_video") as open_video,
            patch.object(processing_service, "analyze_video") as analyze_video,
        ):
            process_request(replace(
                self.request(ProcessingMode.READING_ORDER, checkpoint),
                progress_callback=messages.append,
            ))

        open_video.assert_not_called()
        analyze_video.assert_not_called()
        perform_ocr.assert_not_called()
        reconstruct.assert_not_called()
        self.assertIn(
            "Loading reading-order checkpoint",
            [progress.message for progress in messages],
        )
        self.assertNotIn("ocr", [progress.stage for progress in messages])

    def test_ocr_resume_runs_reading_order_but_skips_video_and_ocr(self):
        checkpoint = self.checkpoint("ocr_results.pkl")
        ocr, reading_order, exporter, create_presentation = self.resume_patches()

        with (
            ocr as perform_ocr,
            reading_order as reconstruct,
            exporter,
            create_presentation,
            patch.object(processing_service, "open_video") as open_video,
            patch.object(processing_service, "analyze_video") as analyze_video,
        ):
            result = process_request(
                self.request(ProcessingMode.OCR_RESULTS, checkpoint)
            )

        open_video.assert_not_called()
        analyze_video.assert_not_called()
        perform_ocr.assert_not_called()
        reconstruct.assert_called_once()
        self.assertTrue((result.run_directory / "cache" / "ocr_results.pkl").is_file())
        self.assertTrue(
            (result.run_directory / "cache" / "reading_order.pkl").is_file()
        )

    def test_candidate_resume_runs_ocr_and_later_stages_only(self):
        checkpoint = self.checkpoint("candidate_frames.pkl")
        ocr, reading_order, exporter, create_presentation = self.resume_patches()

        with (
            ocr as perform_ocr,
            reading_order as reconstruct,
            exporter,
            create_presentation,
            patch.object(processing_service, "open_video") as open_video,
            patch.object(processing_service, "analyze_video") as analyze_video,
            patch.object(processing_service, "save_candidate_frames"),
        ):
            result = process_request(
                self.request(ProcessingMode.CANDIDATE_FRAMES, checkpoint)
            )

        open_video.assert_not_called()
        analyze_video.assert_not_called()
        perform_ocr.assert_called_once()
        reconstruct.assert_called_once()
        self.assertTrue(
            (result.run_directory / "cache" / "candidate_frames.pkl").is_file()
        )
        self.assertTrue((result.run_directory / "cache" / "ocr_results.pkl").is_file())
        self.assertTrue(
            (result.run_directory / "cache" / "reading_order.pkl").is_file()
        )

    def test_run_directory_and_direct_checkpoint_resolution(self):
        checkpoint = self.checkpoint("ocr_results.pkl")

        self.assertEqual(
            resolve_checkpoint_path(ProcessingMode.OCR_RESULTS, checkpoint),
            checkpoint,
        )
        self.assertEqual(
            resolve_checkpoint_path(ProcessingMode.OCR_RESULTS, checkpoint.parent.parent),
            checkpoint,
        )

    def test_missing_checkpoint_has_clear_validation_error(self):
        missing_run = self.root / "missing_run"
        missing_run.mkdir()

        with self.assertRaisesRegex(
            CheckpointValidationError,
            "reading order.*reading_order.pkl.*absent",
        ):
            resolve_checkpoint_path(ProcessingMode.READING_ORDER, missing_run)

    def test_unreadable_checkpoint_has_clear_load_error(self):
        checkpoint = self.root / "sample" / "cache" / "ocr_results.pkl"
        checkpoint.parent.mkdir(parents=True)
        checkpoint.write_bytes(b"not a pickle")

        with self.assertRaisesRegex(
            CheckpointLoadError,
            "ocr results.*could not be loaded",
        ):
            process_request(self.request(ProcessingMode.OCR_RESULTS, checkpoint))

    def test_resumed_workspace_is_new_and_preserves_source_checkpoint(self):
        checkpoint = self.checkpoint("reading_order.pkl")
        original_bytes = checkpoint.read_bytes()
        ocr, reading_order, exporter, create_presentation = self.resume_patches()

        with ocr, reading_order, exporter, create_presentation:
            result = process_request(
                self.request(ProcessingMode.READING_ORDER, checkpoint.parent.parent)
            )

        self.assertEqual(checkpoint.read_bytes(), original_bytes)
        self.assertEqual(result.run_directory.name, "sample_replay")
        self.assertNotEqual(result.run_directory, checkpoint.parent.parent)
        self.assertTrue((result.run_directory / "cache" / "reading_order.pkl").is_file())

    def test_full_video_mode_remains_functional(self):
        video = MagicMock()
        video_path = self.root / "source.mp4"
        video_path.touch()
        request = self.request(ProcessingMode.FULL_VIDEO, video_path)

        with (
            patch.object(processing_service, "open_video", return_value=(video, 30)),
            patch.object(processing_service, "analyze_video", return_value=[]) as analyze_video,
            patch.object(processing_service, "save_candidate_frames"),
            patch.object(processing_service, "perform_ocr", side_effect=lambda frames, **_: frames),
            patch.object(
                processing_service,
                "reconstruct_reading_order",
                side_effect=lambda frames, **_: frames,
            ),
            patch.object(processing_service, "export_all", return_value={}),
        ):
            result = process_request(request)

        analyze_video.assert_called_once()
        video.release.assert_called_once()
        self.assertTrue((result.run_directory / "cache" / "candidate_frames.pkl").is_file())
        self.assertTrue((result.run_directory / "cache" / "ocr_results.pkl").is_file())
        self.assertTrue((result.run_directory / "cache" / "reading_order.pkl").is_file())

    def test_full_processing_uses_the_resolved_local_video_path(self):
        video = MagicMock()
        downloaded_path = self.root / "temporary-download" / "lesson.mp4"
        downloaded_path.parent.mkdir()
        downloaded_path.write_bytes(b"video")
        resolved_source = MagicMock(local_path=downloaded_path)
        request = ProcessingRequest(
            mode=ProcessingMode.FULL_VIDEO,
            source_path="https://example.test/lesson.mp4",
            output_directory=self.output_root,
            formats=["markdown"],
        )

        with (
            patch.object(processing_service, "resolve_video_source", return_value=resolved_source),
            patch.object(processing_service, "open_video", return_value=(video, 30)) as open_video,
            patch.object(processing_service, "get_video_frame_count", return_value=1),
            patch.object(processing_service, "analyze_video", return_value=[]),
            patch.object(processing_service, "save_candidate_frames"),
            patch.object(processing_service, "perform_ocr", side_effect=lambda frames, **_: frames),
            patch.object(processing_service, "reconstruct_reading_order", side_effect=lambda frames, **_: frames),
            patch.object(processing_service, "export_all", return_value={}),
        ):
            process_request(request)

        open_video.assert_called_once_with(str(downloaded_path))
        resolved_source.cleanup.assert_called_once()

    def test_replay_never_resolves_or_downloads_a_video_source(self):
        checkpoint = self.checkpoint("reading_order.pkl")
        ocr, reading_order, exporter, create_presentation = self.resume_patches()

        with (
            ocr,
            reading_order,
            exporter,
            create_presentation,
            patch.object(processing_service, "resolve_video_source") as resolve_source,
        ):
            process_request(self.request(ProcessingMode.READING_ORDER, checkpoint))

        resolve_source.assert_not_called()

    def test_cli_and_gui_delegate_to_the_shared_service(self):
        self.assertIn("process_request(", inspect.getsource(main.process_video))
        self.assertIn("process_request(request)", inspect.getsource(gui.VideoTextApp._run_processing_worker))
        self.assertNotIn("perform_ocr", inspect.getsource(gui))


if __name__ == "__main__":
    unittest.main()
