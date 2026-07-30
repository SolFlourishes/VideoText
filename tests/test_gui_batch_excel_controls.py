"""Focused state-handling tests for the batch Excel GUI controls."""

from pathlib import Path
from types import SimpleNamespace
import sys
import unittest
from unittest.mock import patch


sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from gui import VideoTextApp
from processing_service import ProcessingMode


class FakeVariable:
    def __init__(self, value):
        self.value = value

    def get(self):
        return self.value

    def set(self, value):
        self.value = value


class FakeInteractiveControl:
    def __init__(self):
        self.states = []

    def configure(self, **kwargs):
        self.states.append(kwargs["state"])


class FakeContainer:
    """Fails if a state is incorrectly applied to a layout-only widget."""

    def configure(self, **kwargs):
        raise AssertionError("Layout containers must not receive a state option")


class BatchExcelControlStateTests(unittest.TestCase):
    def make_app(self, mode="single", excel_selected=True):
        return SimpleNamespace(
            run_mode=FakeVariable(mode),
            format_options={"excel": FakeVariable(excel_selected)},
            batch_excel_consolidated=FakeVariable(True),
            batch_excel_controls=[FakeInteractiveControl(), FakeInteractiveControl()],
            # Included to make an accidental return to container state handling fail.
            batch_excel_frame=FakeContainer(),
        )

    def test_initial_single_mode_disables_only_interactive_excel_controls(self):
        app = self.make_app(mode="single", excel_selected=True)

        VideoTextApp._update_batch_excel_options(app)

        self.assertEqual(
            [control.states for control in app.batch_excel_controls],
            [["disabled"], ["disabled"]],
        )
        self.assertFalse(app.batch_excel_consolidated.get())

    def test_batch_mode_enables_controls_only_when_excel_is_selected(self):
        enabled_app = self.make_app(mode="batch", excel_selected=True)
        VideoTextApp._update_batch_excel_options(enabled_app)
        self.assertEqual(
            [control.states for control in enabled_app.batch_excel_controls],
            [["normal"], ["normal"]],
        )
        self.assertTrue(enabled_app.batch_excel_consolidated.get())

        disabled_app = self.make_app(mode="batch", excel_selected=False)
        VideoTextApp._update_batch_excel_options(disabled_app)
        self.assertEqual(
            [control.states for control in disabled_app.batch_excel_controls],
            [["disabled"], ["disabled"]],
        )
        self.assertFalse(disabled_app.batch_excel_consolidated.get())


class ReplayStartTests(unittest.TestCase):
    def test_existing_checkpoint_starts_replay_without_a_name_error(self):
        with self.subTest("the source and output paths both exist"):
            from tempfile import TemporaryDirectory

            with TemporaryDirectory() as temporary_directory:
                root = Path(temporary_directory)
                checkpoint = root / "reading_order.pkl"
                checkpoint.touch()
                app = SimpleNamespace(
                    processing=False,
                    run_mode=FakeVariable("single"),
                    advanced_mode=FakeVariable(True),
                    advanced_start_mode=FakeVariable(ProcessingMode.READING_ORDER.value),
                    advanced_source_path=FakeVariable(str(checkpoint)),
                    video_path=FakeVariable(""),
                    output_folder=FakeVariable(str(root)),
                    format_options={"markdown": FakeVariable(True)},
                    process_button=FakeInteractiveControl(),
                    _reset_progress=lambda: None,
                    _append_log=lambda _message: None,
                    _run_processing_worker=lambda _request: None,
                    _queue_progress=lambda _progress: None,
                    _poll_worker_messages=lambda: None,
                    after=lambda *_args: None,
                )

                with patch("gui.threading.Thread") as thread:
                    VideoTextApp._start_processing(app)

                self.assertTrue(app.processing)
                self.assertEqual(app.process_button.states, ["disabled"])
                thread.assert_called_once()


if __name__ == "__main__":
    unittest.main()
