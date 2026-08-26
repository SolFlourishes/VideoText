"""Focused tests for shared full and resumed VideoText processing."""

import inspect
from contextlib import ExitStack
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
from models import CandidateFrame, Presentation, TextParagraph, TextType
from ocr_diagnostics import DiagnosticError, DiagnosticOptions
from processing_service import (
    CheckpointLoadError,
    CheckpointValidationError,
    ProcessingMode,
    ProcessingRequest,
    process_request,
    reconstruct_presentation_from_reading_order,
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

    def reading_order_frame(self, text: str = "Preserved paragraph") -> CandidateFrame:
        return CandidateFrame(
            frame_number=12,
            timestamp=2.5,
            image=None,
            difference_score=0.0,
            text_paragraphs=[TextParagraph(text, text_type=TextType.BODY)],
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

    def test_read_only_reconstruction_accepts_completed_run_directory(self):
        checkpoint = self.checkpoint(
            "reading_order.pkl",
            [self.reading_order_frame("Expected slide paragraph")],
        )

        resolved, presentation = reconstruct_presentation_from_reading_order(
            checkpoint.parent.parent
        )

        self.assertEqual(checkpoint, resolved)
        self.assertEqual("Expected slide paragraph", presentation.slides[0].paragraphs[0].text)
        self.assertEqual(str(checkpoint), presentation.metadata["source_checkpoint"])
        self.assertEqual(ProcessingMode.READING_ORDER.value, presentation.metadata["processing_mode"])
        self.assertEqual(checkpoint, presentation.metadata["resolved_checkpoint_path"])

    def test_read_only_reconstruction_accepts_direct_checkpoint_path(self):
        checkpoint = self.checkpoint(
            "reading_order.pkl",
            [self.reading_order_frame("Direct checkpoint paragraph")],
        )

        resolved, presentation = reconstruct_presentation_from_reading_order(checkpoint)

        self.assertEqual(checkpoint, resolved)
        self.assertEqual("Direct checkpoint paragraph", presentation.slides[0].paragraphs[0].text)

    def test_read_only_reconstruction_missing_cache_preserves_validation_error(self):
        completed_run = self.root / "missing"
        completed_run.mkdir()

        with self.assertRaisesRegex(
            CheckpointValidationError,
            "reading order.*reading_order.pkl.*absent",
        ):
            reconstruct_presentation_from_reading_order(completed_run)

    def test_read_only_reconstruction_corrupted_cache_preserves_load_error(self):
        checkpoint = self.root / "corrupted" / "cache" / "reading_order.pkl"
        checkpoint.parent.mkdir(parents=True)
        checkpoint.write_bytes(b"not a pickle")

        with self.assertRaisesRegex(
            CheckpointLoadError,
            "reading order.*could not be loaded",
        ):
            reconstruct_presentation_from_reading_order(checkpoint)

    def test_read_only_reconstruction_rejects_structurally_incompatible_cache(self):
        checkpoint = self.checkpoint("reading_order.pkl", {"unexpected": "data"})

        with self.assertRaisesRegex(
            CheckpointLoadError,
            "contains incompatible data.*Expected a list of CandidateFrame",
        ):
            reconstruct_presentation_from_reading_order(checkpoint)

    def test_read_only_reconstruction_preserves_source_and_creates_nothing(self):
        checkpoint = self.checkpoint(
            "reading_order.pkl",
            [self.reading_order_frame()],
        )
        original_bytes = checkpoint.read_bytes()
        paths_before = {path.relative_to(self.root) for path in self.root.rglob("*")}

        prohibited = (
            "process_request", "create_replay_run_directory", "save_cache",
            "export_all", "resolve_video_source", "open_video", "analyze_video",
            "perform_ocr", "reconstruct_reading_order",
        )
        with ExitStack() as stack:
            for name in prohibited:
                stack.enter_context(
                    patch.object(processing_service, name, side_effect=AssertionError(name))
                )
            resolved, presentation = reconstruct_presentation_from_reading_order(
                checkpoint.parent.parent
            )

        self.assertEqual(checkpoint, resolved)
        self.assertIsInstance(presentation, Presentation)
        self.assertEqual(original_bytes, checkpoint.read_bytes())
        self.assertEqual(paths_before, {path.relative_to(self.root) for path in self.root.rglob("*")})

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
        self.assertFalse((result.run_directory / "diagnostics").exists())

    def test_full_video_releases_decoder_before_paddle_ocr_starts(self):
        video = MagicMock()
        video_path = self.root / "decoder-boundary.mp4"
        video_path.touch()

        def assert_decoder_released(frames, **_kwargs):
            video.release.assert_called_once()
            return frames

        with (
            patch.object(processing_service, "open_video", return_value=(video, 30)),
            patch.object(processing_service, "analyze_video", return_value=[]),
            patch.object(processing_service, "save_candidate_frames"),
            patch.object(processing_service, "perform_ocr", side_effect=assert_decoder_released),
            patch.object(processing_service, "reconstruct_reading_order", side_effect=lambda frames, **_: frames),
            patch.object(processing_service, "export_all", return_value={}),
        ):
            process_request(self.request(ProcessingMode.FULL_VIDEO, video_path))

    def test_non_strict_diagnostic_failure_does_not_fail_processing(self):
        checkpoint = self.checkpoint("reading_order.pkl")
        request = ProcessingRequest(
            mode=ProcessingMode.READING_ORDER,
            source_path=str(checkpoint),
            output_directory=self.output_root,
            formats=["markdown"],
            diagnostic_options=DiagnosticOptions(
                output_directory=self.root / "diagnostics",
                all_candidate_frames=True,
            ),
        )
        ocr, reading_order, exporter, create_presentation = self.resume_patches()

        with (
            ocr,
            reading_order,
            exporter,
            create_presentation,
            patch.object(processing_service.OCRDiagnosticsWriter, "write", side_effect=DiagnosticError("disk unavailable")),
        ):
            result = process_request(request)

        self.assertEqual(result.mode, ProcessingMode.READING_ORDER)

    def test_strict_diagnostic_failure_is_surfaced(self):
        checkpoint = self.checkpoint("reading_order.pkl")
        request = ProcessingRequest(
            mode=ProcessingMode.READING_ORDER,
            source_path=str(checkpoint),
            output_directory=self.output_root,
            formats=["markdown"],
            diagnostic_options=DiagnosticOptions(
                output_directory=self.root / "diagnostics",
                all_candidate_frames=True,
                strict=True,
            ),
        )
        ocr, reading_order, exporter, create_presentation = self.resume_patches()

        with (
            ocr,
            reading_order,
            exporter,
            create_presentation,
            patch.object(processing_service.OCRDiagnosticsWriter, "write", side_effect=DiagnosticError("disk unavailable")),
            self.assertRaisesRegex(DiagnosticError, "disk unavailable"),
        ):
            process_request(request)

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
