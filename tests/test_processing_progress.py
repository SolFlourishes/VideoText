"""Focused tests for shared processing progress, timing, and ETA."""

import pickle
import sys
import tempfile
from pathlib import Path
import unittest
from unittest.mock import MagicMock, patch


sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import gui
import processing_service
from models import Presentation
from processing_service import (
    ProcessingMode,
    ProcessingProgress,
    ProcessingRequest,
    ProgressReporter,
    format_duration,
    process_request,
)


class FakeClock:
    def __init__(self):
        self.value = 0.0

    def __call__(self):
        return self.value


class FakeValue:
    def __init__(self):
        self.value = None

    def set(self, value):
        self.value = value


class FakeProgressBar:
    def __init__(self):
        self.configurations = []
        self.started = False

    def configure(self, **kwargs):
        self.configurations.append(kwargs)

    def start(self, _interval):
        self.started = True

    def stop(self):
        self.started = False


class ProcessingProgressTests(unittest.TestCase):
    def setUp(self):
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary_directory.cleanup)
        self.root = Path(self.temporary_directory.name)

    def checkpoint(self, name: str, frames: list[object]) -> Path:
        checkpoint = self.root / "sample" / "cache" / name
        checkpoint.parent.mkdir(parents=True, exist_ok=True)
        with checkpoint.open("wb") as file:
            pickle.dump(frames, file)
        return checkpoint

    def request(self, mode, checkpoint, events):
        return ProcessingRequest(
            mode=mode,
            source_path=str(checkpoint),
            output_directory=self.root / "output",
            formats=["markdown", "csv", "excel"],
            progress_callback=events.append,
        )

    def test_eta_is_absent_until_three_completed_items(self):
        clock = FakeClock()
        events = []
        reporter = ProgressReporter(events.append, clock=clock)
        reporter.stage("ocr", "Running OCR")
        clock.value = 8
        reporter.item("ocr", "Running OCR", 2, 5)

        self.assertIsNone(events[-1].estimated_remaining_seconds)

    def test_eta_uses_elapsed_time_and_remaining_items_after_three(self):
        clock = FakeClock()
        events = []
        reporter = ProgressReporter(events.append, clock=clock)
        reporter.stage("ocr", "Running OCR")
        clock.value = 12
        reporter.item("ocr", "Running OCR", 3, 5)

        self.assertEqual(events[-1].elapsed_seconds, 12)
        self.assertEqual(events[-1].estimated_remaining_seconds, 8)

    def test_eta_is_never_negative(self):
        clock = FakeClock()
        events = []
        reporter = ProgressReporter(events.append, clock=clock)
        reporter.stage("ocr", "Running OCR")
        clock.value = 6
        reporter.item("ocr", "Running OCR", 6, 5)

        self.assertEqual(events[-1].estimated_remaining_seconds, 0)

    def test_frame_eta_waits_for_frame_and_time_thresholds(self):
        clock = FakeClock()
        events = []
        reporter = ProgressReporter(events.append, clock=clock)
        reporter.stage("frame_selection", "Selecting stable frames")

        clock.value = 4
        reporter.frame_selection(500, 1000)
        self.assertIsNone(events[-1].estimated_remaining_seconds)

        clock.value = 5
        reporter.frame_selection(500, 1000)
        self.assertEqual(events[-1].percentage, 50)
        self.assertEqual(events[-1].estimated_remaining_seconds, 5)

    def test_frame_progress_with_unknown_total_has_no_percentage_or_eta(self):
        clock = FakeClock()
        events = []
        reporter = ProgressReporter(events.append, clock=clock)
        reporter.stage("frame_selection", "Selecting stable frames")
        clock.value = 10
        reporter.frame_selection(1000, None)

        self.assertIsNone(events[-1].total)
        self.assertIsNone(events[-1].percentage)
        self.assertIsNone(events[-1].estimated_remaining_seconds)

    def test_ocr_progress_covers_every_candidate_frame(self):
        frames = [object(), object(), object(), object()]
        checkpoint = self.checkpoint("candidate_frames.pkl", frames)
        events = []

        def ocr(candidate_frames, progress_callback):
            for current in range(1, len(candidate_frames) + 1):
                progress_callback(current, len(candidate_frames))
            return candidate_frames

        with (
            patch.object(processing_service, "perform_ocr", side_effect=ocr),
            patch.object(processing_service, "save_candidate_frames"),
            patch.object(
                processing_service,
                "reconstruct_reading_order",
                side_effect=lambda frames, **_: frames,
            ),
            patch.object(processing_service, "_create_presentation", return_value=Presentation()),
            patch.object(processing_service, "export_all", return_value={}),
        ):
            process_request(self.request(ProcessingMode.CANDIDATE_FRAMES, checkpoint, events))

        self.assertEqual(
            [
                event.current
                for event in events
                if event.stage == "ocr" and event.current is not None
            ],
            [1, 2, 3, 4],
        )

    def test_reading_order_progress_covers_every_ocr_frame(self):
        frames = [object(), object(), object()]
        checkpoint = self.checkpoint("ocr_results.pkl", frames)
        events = []

        def reading_order(candidate_frames, progress_callback):
            for current in range(1, len(candidate_frames) + 1):
                progress_callback(current, len(candidate_frames))
            return candidate_frames

        with (
            patch.object(processing_service, "perform_ocr") as ocr,
            patch.object(processing_service, "reconstruct_reading_order", side_effect=reading_order),
            patch.object(processing_service, "_create_presentation", return_value=Presentation()),
            patch.object(processing_service, "export_all", return_value={}),
        ):
            process_request(self.request(ProcessingMode.OCR_RESULTS, checkpoint, events))

        ocr.assert_not_called()
        self.assertEqual(
            [
                event.current
                for event in events
                if event.stage == "reading_order" and event.current is not None
            ],
            [1, 2, 3],
        )

    def test_export_progress_matches_selected_formats(self):
        checkpoint = self.checkpoint("reading_order.pkl", [])
        events = []

        def export_all(*_args, progress_callback, **_kwargs):
            for current in range(1, 4):
                progress_callback(current, 3)
            return {}

        with (
            patch.object(processing_service, "_create_presentation", return_value=Presentation()),
            patch.object(processing_service, "export_all", side_effect=export_all),
        ):
            process_request(self.request(ProcessingMode.READING_ORDER, checkpoint, events))

        self.assertEqual(
            [
                event.current
                for event in events
                if event.stage == "export" and event.current is not None
            ],
            [1, 2, 3],
        )

    def test_resume_modes_emit_only_their_actual_work(self):
        reading_checkpoint = self.checkpoint("reading_order.pkl", [])
        ocr_checkpoint = self.checkpoint("ocr_results.pkl", [])
        reading_events = []
        ocr_events = []

        with (
            patch.object(processing_service, "perform_ocr") as ocr,
            patch.object(
                processing_service,
                "reconstruct_reading_order",
                side_effect=lambda frames, **_: frames,
            ),
            patch.object(processing_service, "_create_presentation", return_value=Presentation()),
            patch.object(processing_service, "export_all", return_value={}),
        ):
            process_request(self.request(ProcessingMode.READING_ORDER, reading_checkpoint, reading_events))
            process_request(self.request(ProcessingMode.OCR_RESULTS, ocr_checkpoint, ocr_events))

        ocr.assert_not_called()
        self.assertNotIn("ocr", [event.stage for event in reading_events])
        self.assertNotIn("ocr", [event.stage for event in ocr_events])
        self.assertIn("reading_order", [event.stage for event in ocr_events])

    def test_full_mode_emits_the_expected_stage_sequence(self):
        video_path = self.root / "video.mp4"
        video_path.touch()
        events = []
        video = MagicMock()
        request = ProcessingRequest(
            mode=ProcessingMode.FULL_VIDEO,
            source_path=str(video_path),
            output_directory=self.root / "output",
            formats=["markdown"],
            progress_callback=events.append,
        )

        with (
            patch.object(processing_service, "open_video", return_value=(video, 30)),
            patch.object(processing_service, "analyze_video", return_value=[]),
            patch.object(processing_service, "save_candidate_frames"),
            patch.object(processing_service, "perform_ocr", side_effect=lambda frames, **_: frames),
            patch.object(processing_service, "reconstruct_reading_order", side_effect=lambda frames, **_: frames),
            patch.object(processing_service, "_create_presentation", return_value=Presentation()),
            patch.object(processing_service, "export_all", return_value={}),
        ):
            process_request(request)

        stages = []
        for event in events:
            if event.stage not in stages:
                stages.append(event.stage)
        self.assertEqual(
            stages,
            [
                "preparing_video",
                "frame_selection",
                "ocr",
                "reading_order",
                "consolidation",
                "export",
                "complete",
            ],
        )

    def test_full_mode_emits_shared_frame_selection_progress(self):
        video_path = self.root / "video.mp4"
        video_path.touch()
        events = []
        video = MagicMock()
        request = ProcessingRequest(
            mode=ProcessingMode.FULL_VIDEO,
            source_path=str(video_path),
            output_directory=self.root / "output",
            formats=["markdown"],
            progress_callback=events.append,
        )

        def analyzer(_video, _fps, progress_callback, total_frames):
            progress_callback(500, total_frames)
            progress_callback(1000, total_frames)
            return []

        with (
            patch.object(processing_service, "open_video", return_value=(video, 30)),
            patch.object(processing_service, "get_video_frame_count", return_value=1000),
            patch.object(processing_service, "analyze_video", side_effect=analyzer),
            patch.object(processing_service, "save_candidate_frames"),
            patch.object(processing_service, "perform_ocr", side_effect=lambda frames, **_: frames),
            patch.object(processing_service, "reconstruct_reading_order", side_effect=lambda frames, **_: frames),
            patch.object(processing_service, "_create_presentation", return_value=Presentation()),
            patch.object(processing_service, "export_all", return_value={}),
        ):
            process_request(request)

        frame_events = [event for event in events if event.stage == "frame_selection" and event.current]
        self.assertEqual([500, 1000], [event.current for event in frame_events])
        self.assertEqual([50, 100], [event.percentage for event in frame_events])

    def test_gui_progress_switches_between_progressbar_modes(self):
        app = object.__new__(gui.VideoTextApp)
        app.progress_bar = FakeProgressBar()
        app.progress_value = FakeValue()
        app.status = FakeValue()
        app.progress_details = FakeValue()
        app._append_log = lambda _message: None

        gui.VideoTextApp._show_progress(app, ProcessingProgress(
            "ocr", "Running OCR", 1, 4, 2, None,
        ))
        self.assertEqual(app.progress_bar.configurations[-1]["mode"], "determinate")
        self.assertEqual(app.progress_value.value, 1)

        gui.VideoTextApp._show_progress(app, ProcessingProgress(
            "consolidation", "Consolidating slides", None, None, 1, None,
        ))
        self.assertEqual(app.progress_bar.configurations[-1]["mode"], "indeterminate")

    def test_gui_frame_progress_and_reset_do_not_leave_stale_eta(self):
        app = object.__new__(gui.VideoTextApp)
        app.progress_bar = FakeProgressBar()
        app.progress_value = FakeValue()
        app.status = FakeValue()
        app.progress_details = FakeValue()
        app._append_log = lambda _message: None

        gui.VideoTextApp._show_progress(app, ProcessingProgress(
            "frame_selection", "Selecting stable frames", 500, 1000, 5, 5, 50,
        ))
        self.assertEqual(app.progress_bar.configurations[-1]["mode"], "determinate")
        self.assertIn("500 / 1,000 frames (50%)", app.status.value)

        gui.VideoTextApp._reset_progress(app)
        self.assertEqual(app.progress_value.value, 0)
        self.assertEqual(app.progress_details.value, "")

    def test_gui_unknown_frame_total_remains_indeterminate_with_count(self):
        app = object.__new__(gui.VideoTextApp)
        app.progress_bar = FakeProgressBar()
        app.progress_value = FakeValue()
        app.status = FakeValue()
        app.progress_details = FakeValue()
        app._append_log = lambda _message: None

        gui.VideoTextApp._show_progress(app, ProcessingProgress(
            "frame_selection", "Selecting stable frames", 750, None, 6, None,
        ))

        self.assertEqual(app.progress_bar.configurations[-1]["mode"], "indeterminate")
        self.assertIn("750 frames processed", app.status.value)
        self.assertNotIn("Estimated remaining", app.progress_details.value)

    def test_duration_formatting_is_compact(self):
        self.assertEqual(format_duration(8), "8 seconds")
        self.assertEqual(format_duration(65), "1m 05s")
        self.assertEqual(format_duration(761), "12m 41s")
        self.assertEqual(format_duration(3780), "1h 03m")


if __name__ == "__main__":
    unittest.main()
