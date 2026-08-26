"""Focused no-display tests for translation GUI workflow decisions."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
import queue
import sys
import tempfile
import unittest
from unittest.mock import patch


sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import gui
from models import Presentation
from processing_service import ProcessingMode, ProcessingResult
from translation_job import TranslationOutputGrouping


class Variable:
    """Small Tk-variable stand-in for deterministic GUI decision tests."""

    def __init__(self, value):
        self.value = value

    def get(self):
        return self.value

    def set(self, value):
        self.value = value


class TranslationGUIWorkflowTests(unittest.TestCase):
    def test_locale_arrow_navigation_wraps_selectable_controls(self):
        self.assertEqual(2, gui._next_locale_control_index(0, 3, -1))
        self.assertEqual(0, gui._next_locale_control_index(2, 3, 1))
        with self.assertRaises(ValueError):
            gui._next_locale_control_index(0, 0, 1)

    def make_configuration_app(self, mode="single", provider="local"):
        return SimpleNamespace(
            translation_enabled=Variable(True),
            translation_languages={"es-419": Variable(True), "nl-NL": Variable(True)},
            translation_provider=Variable(provider),
            translation_formats={"excel": Variable(True), "csv": Variable(False), "markdown": Variable(False)},
            local_translation_availability=SimpleNamespace(
                installed_pairs=(("en", "es-419"), ("en", "nl-NL")),
            ),
            translation_grouping=Variable(TranslationOutputGrouping.BY_LANGUAGE.value),
            run_mode=Variable(mode),
            translation_model=Variable("Recommended"),
            _set_status=lambda _message: self.fail("configuration should be valid"),
        )

    def test_single_mode_forces_one_workbook_per_video(self):
        app = self.make_configuration_app()

        configuration = gui.VideoTextApp._translation_configuration(app)

        self.assertEqual(TranslationOutputGrouping.BY_SOURCE, configuration[2])

    def test_batch_mode_retains_selected_grouping(self):
        app = self.make_configuration_app(mode="batch")

        configuration = gui.VideoTextApp._translation_configuration(app)

        self.assertEqual(TranslationOutputGrouping.BY_LANGUAGE, configuration[2])

    def test_local_availability_is_exact_and_selected_order_is_deterministic(self):
        app = SimpleNamespace(
            translation_provider=Variable("local"),
            translation_languages={"es-419": Variable(True), "ko-KR": Variable(False), "nl-NL": Variable(True)},
            local_translation_availability=SimpleNamespace(
                installed_pairs=(("en", "nl-NL"), ("en", "es-419")),
            ),
            translation_locale_summary=Variable(""),
        )
        app._available_translation_targets = lambda: gui.VideoTextApp._available_translation_targets(app)
        with patch.object(gui, "TRANSLATION_TARGET_LOCALES", (
            ("es-419", "Spanish — Latin America"),
            ("ko-KR", "Korean — South Korea"),
            ("nl-NL", "Dutch — Netherlands"),
        )):
            self.assertEqual({"es-419", "nl-NL"}, gui.VideoTextApp._available_translation_targets(app))
            gui.VideoTextApp._update_translation_summary(app)

        self.assertEqual("Spanish — Latin America; Dutch — Netherlands", app.translation_locale_summary.get())

    def test_english_canada_is_cloud_available_but_not_local_without_an_exact_model(self):
        app = SimpleNamespace(
            translation_provider=Variable("openai"),
            translation_languages={"en-CA": Variable(False), "es-419": Variable(False)},
            local_translation_availability=SimpleNamespace(installed_pairs=(("en", "es-419"),)),
        )

        self.assertEqual({"en-CA", "es-419"}, gui.VideoTextApp._available_translation_targets(app))
        app.translation_provider.set("local")
        self.assertEqual({"es-419"}, gui.VideoTextApp._available_translation_targets(app))

    def test_local_provider_is_not_constructed_when_ocr_processing_fails(self):
        app = object.__new__(gui.VideoTextApp)
        app.message_queue = queue.Queue()
        request = SimpleNamespace(mode=ProcessingMode.FULL_VIDEO)
        with (
            patch.object(gui, "process_request", side_effect=RuntimeError("OCR failed")),
            patch.object(gui, "LocalCTranslate2Provider") as local_provider,
            patch.object(gui, "write_gui_diagnostic", return_value=Path("diagnostic.log")),
        ):
            gui.VideoTextApp._run_processing_worker(app, request, ("local", ("es-419",), TranslationOutputGrouping.BY_SOURCE, ("excel",), None, None))

        local_provider.assert_not_called()
        message_type, message = app.message_queue.get_nowait()
        self.assertEqual("error", message_type)
        self.assertIn("RuntimeError: OCR failed", message)
        self.assertIn("Diagnostic log", message)

    def test_openai_construction_failure_stops_before_translation_job(self):
        app = object.__new__(gui.VideoTextApp)
        app.message_queue = queue.Queue()
        result = ProcessingResult(Presentation(), Path("output/run"), {}, ProcessingMode.FULL_VIDEO,
                                  "video.mp4", None, 0, 0.0)
        configuration = ("openai", ("es-419",), TranslationOutputGrouping.BY_SOURCE,
                         ("excel",), "sk-DISTINCTIVE-TEST-KEY", "gpt-4.1-mini")
        with (
            patch.object(gui, "OpenAITranslationProvider") as provider_class,
            patch.object(gui, "run_translation_job") as run_job,
        ):
            provider_class.return_value.ensure_ready.side_effect = ValueError("OpenAI SDK unavailable")
            with self.assertRaises(ValueError):
                gui.VideoTextApp._translate_completed_results(app, (result,), configuration, Path("output/run/translations"))
        run_job.assert_not_called()

    def test_single_translation_output_is_under_its_run_directory(self):
        app = object.__new__(gui.VideoTextApp)
        app.message_queue = queue.Queue()
        app.local_translation_model_root = Path(tempfile.gettempdir())
        with tempfile.TemporaryDirectory() as temporary_directory:
            run_directory = Path(temporary_directory) / "video-run"
            result = ProcessingResult(Presentation(), run_directory, {}, ProcessingMode.FULL_VIDEO,
                                      "video.mp4", None, 0, 0.0)
            configuration = ("local", ("es-419",), TranslationOutputGrouping.BY_SOURCE,
                             ("excel",), None, None)
            expected_directory = run_directory / "translations"
            with (
                patch.object(gui, "LocalCTranslate2Provider"),
                patch.object(gui, "run_translation_job", return_value="translated") as run_job,
                patch.object(gui, "write_gui_diagnostic"),
            ):
                output = gui.VideoTextApp._translate_completed_results(
                    app, (result,), configuration, expected_directory,
                )

        self.assertEqual("translated", output)
        self.assertEqual(expected_directory, run_job.call_args.args[7])

    def test_replay_translation_identity_uses_the_originating_ocr_export(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            source_run = Path(temporary_directory) / "sample2_4"
            cache = source_run / "cache"
            cache.mkdir(parents=True)
            (source_run / "sample2.md").write_text("source", encoding="utf-8")
            first_replay = Path(temporary_directory) / "sample2_4_replay"
            (first_replay / "cache").mkdir(parents=True)
            checkpoint = first_replay / "cache" / "ocr_results.pkl"
            checkpoint.touch()
            result = ProcessingResult(
                Presentation(), Path(temporary_directory) / "sample2_4_replay_replay", {},
                ProcessingMode.OCR_RESULTS, str(checkpoint), checkpoint, 49, 0.0,
            )

            identity = gui._translation_source_identity(result)

        self.assertEqual("sample2", identity)


if __name__ == "__main__":
    unittest.main()
