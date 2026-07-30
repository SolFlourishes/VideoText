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
    PHASE_STAGES,
    ProcessingMode,
    ProcessingProgress,
    ProcessingRequest,
    ProgressReporter,
    format_bytes,
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

    def test_non_ocr_eta_is_absent_until_three_completed_items(self):
        clock = FakeClock()
        events = []
        reporter = ProgressReporter(events.append, clock=clock)
        reporter.stage("reading_order", "Determining reading order")
        clock.value = 8
        reporter.item("reading_order", "Determining reading order", 2, 5)

        self.assertIsNone(events[-1].estimated_remaining_seconds)

    def test_non_ocr_eta_uses_elapsed_time_and_remaining_items_after_three(self):
        clock = FakeClock()
        events = []
        reporter = ProgressReporter(events.append, clock=clock)
        reporter.stage("reading_order", "Determining reading order")
        clock.value = 12
        reporter.item("reading_order", "Determining reading order", 3, 5)

        self.assertEqual(events[-1].elapsed_seconds, 12)
        self.assertEqual(events[-1].estimated_remaining_seconds, 8)

    def test_eta_is_never_negative(self):
        clock = FakeClock()
        events = []
        reporter = ProgressReporter(events.append, clock=clock)
        reporter.stage("reading_order", "Determining reading order")
        clock.value = 6
        reporter.item("reading_order", "Determining reading order", 6, 5)

        self.assertEqual(events[-1].estimated_remaining_seconds, 0)

    def test_ocr_eta_requires_five_items_and_ten_seconds(self):
        clock = FakeClock()
        events = []
        reporter = ProgressReporter(events.append, phase_stages=("ocr",), clock=clock)
        reporter.stage("ocr", "Running OCR")

        clock.value = 10
        reporter.item("ocr", "Running OCR", 4, 65)
        self.assertIsNone(events[-1].estimated_remaining_seconds)

        clock.value = 9
        reporter.item("ocr", "Running OCR", 5, 65)
        self.assertIsNone(events[-1].estimated_remaining_seconds)

        clock.value = 10
        reporter.item("ocr", "Running OCR", 5, 65)
        self.assertEqual(events[-1].estimated_remaining_seconds, 120)
        self.assertEqual(events[-1].step_current, 1)
        self.assertEqual(events[-1].step_total, 1)

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

    def test_download_progress_is_step_zero_before_pipeline_phases(self):
        clock = FakeClock()
        events = []
        reporter = ProgressReporter(
            events.append,
            phase_stages=PHASE_STAGES[ProcessingMode.FULL_VIDEO],
            clock=clock,
        )

        clock.value = 4
        reporter.download(2048, 4096)

        event = events[-1]
        self.assertEqual((event.stage, event.step_current, event.step_total), ("download", 0, 5))
        self.assertEqual(event.percentage, 50)
        self.assertEqual(format_bytes(event.current), "2.0 KB")

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
        phase_events = [event for event in events if event.step_current is not None]
        self.assertEqual(
            [(event.stage, event.step_current, event.step_total) for event in phase_events if event.current is None],
            [
                ("frame_selection", 1, 5),
                ("ocr", 2, 5),
                ("reading_order", 3, 5),
                ("consolidation", 4, 5),
                ("export", 5, 5),
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

    def test_gui_download_progress_uses_bytes_and_step_zero(self):
        app = object.__new__(gui.VideoTextApp)
        app.progress_bar = FakeProgressBar()
        app.progress_value = FakeValue()
        app.status = FakeValue()
        app.progress_details = FakeValue()
        app._append_log = lambda _message: None

        gui.VideoTextApp._show_progress(app, ProcessingProgress(
            "download", "Downloading video", 2048, 4096, 4, 4, 50, 0, 5,
        ))

        self.assertEqual(app.progress_bar.configurations[-1]["mode"], "determinate")
        self.assertIn("Step 0 of 5", app.status.value)
        self.assertIn("2.0 KB of 4.0 KB (50%)", app.status.value)

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

    def test_gui_stage_transition_clears_frame_counts_and_eta(self):
        app = object.__new__(gui.VideoTextApp)
        app.progress_bar = FakeProgressBar()
        app.progress_value = FakeValue()
        app.status = FakeValue()
        app.progress_details = FakeValue()
        app._append_log = lambda _message: None

        gui.VideoTextApp._show_progress(app, ProcessingProgress(
            "frame_selection", "Selecting stable frames", 900, 1000, 10, 1, 90, 1, 5,
        ))
        gui.VideoTextApp._show_progress(app, ProcessingProgress(
            "ocr", "Running OCR", None, None, 0, None, None, 2, 5,
        ))

        self.assertEqual(app.progress_bar.configurations[-1]["mode"], "indeterminate")
        self.assertIn("Step 2 of 5", app.status.value)
        self.assertNotIn("900", app.status.value)
        self.assertNotIn("Estimated", app.progress_details.value)
        self.assertEqual(app.progress_details.value, "Phase elapsed: 0 seconds")

    def test_reading_order_replay_numbers_only_its_two_executed_steps(self):
        checkpoint = self.checkpoint("reading_order.pkl", [])
        events = []

        with (
            patch.object(processing_service, "_create_presentation", return_value=Presentation()),
            patch.object(processing_service, "export_all", return_value={}),
        ):
            process_request(self.request(ProcessingMode.READING_ORDER, checkpoint, events))

        phases = [
            (event.stage, event.step_current, event.step_total)
            for event in events
            if event.step_current is not None and event.current is None
        ]
        self.assertEqual(phases, [("consolidation", 1, 2), ("export", 2, 2)])

    def test_phase_plans_exclude_skipped_replay_stages(self):
        self.assertEqual(
            PHASE_STAGES[ProcessingMode.FULL_VIDEO],
            ("frame_selection", "ocr", "reading_order", "consolidation", "export"),
        )
        self.assertEqual(
            PHASE_STAGES[ProcessingMode.CANDIDATE_FRAMES],
            ("ocr", "reading_order", "consolidation", "export"),
        )
        self.assertEqual(
            PHASE_STAGES[ProcessingMode.OCR_RESULTS],
            ("reading_order", "consolidation", "export"),
        )
        self.assertEqual(
            PHASE_STAGES[ProcessingMode.READING_ORDER],
            ("consolidation", "export"),
        )

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
