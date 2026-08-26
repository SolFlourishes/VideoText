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
from existing_results_translation import (
    DuplicateExistingResult,
    ExistingResultsTranslationPreparation,
    InvalidExistingResult,
    ValidExistingResult,
)
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


class Widget:
    """Small configurable-widget stand-in for provider callback tests."""

    def __init__(self):
        self.options = {}

    def configure(self, **options):
        self.options.update(options)


class Listbox:
    def __init__(self, selected=()):
        self.values = []
        self.selected = selected

    def delete(self, *_args):
        self.values.clear()

    def insert(self, _position, value):
        self.values.append(value)

    def curselection(self):
        return self.selected


class TranslationGUIWorkflowTests(unittest.TestCase):
    def test_file_menu_exposes_existing_results_workflow(self):
        source = Path(gui.__file__).read_text(encoding="utf-8")
        self.assertIn('label="Batch Translate Existing Results..."', source)
        self.assertIn("command=self._show_existing_results_translation", source)

    def make_existing_selection_app(self):
        app = SimpleNamespace(
            existing_result_paths=[],
            existing_results_listbox=Listbox(),
            existing_status=Variable(""),
        )
        app._refresh_existing_results_list = lambda: gui.VideoTextApp._refresh_existing_results_list(app)
        return app

    def test_existing_result_selection_preserves_order_and_prevents_duplicates(self):
        app = self.make_existing_selection_app()
        with tempfile.TemporaryDirectory() as temporary_directory:
            first = Path(temporary_directory) / "first"
            second = Path(temporary_directory) / "second"
            first.mkdir(); second.mkdir()
            self.assertTrue(gui.VideoTextApp._add_existing_result_path(app, first))
            self.assertTrue(gui.VideoTextApp._add_existing_result_path(app, second))
            self.assertFalse(gui.VideoTextApp._add_existing_result_path(app, first))

        self.assertEqual([str(first), str(second)], app.existing_result_paths)
        self.assertEqual([str(first), str(second)], app.existing_results_listbox.values)

    def test_existing_result_selection_remove_and_clear(self):
        app = self.make_existing_selection_app()
        app.existing_result_paths[:] = ["first", "second"]
        app.existing_results_listbox.selected = (0,)
        gui.VideoTextApp._remove_selected_existing_result(app)
        self.assertEqual(["second"], app.existing_result_paths)
        gui.VideoTextApp._clear_existing_results(app)
        self.assertEqual([], app.existing_result_paths)
        self.assertEqual([], app.existing_results_listbox.values)

    def make_existing_settings_app(self, provider="local"):
        app = SimpleNamespace(
            existing_result_paths=["run"],
            existing_output_root=Variable(tempfile.gettempdir()),
            existing_provider=Variable(provider),
            existing_languages={"en-CA": Variable(False), "pt-BR": Variable(True)},
            existing_formats={"excel": Variable(True), "csv": Variable(False)},
            existing_grouping=Variable(TranslationOutputGrouping.BY_SOURCE.value),
            existing_model=Variable("Recommended"),
            existing_status=Variable(""),
            existing_local_provider_control=Widget(),
            local_translation_availability=SimpleNamespace(
                installed_pairs=(("en", "pt-BR"),), installed_models=("model",),
            ),
        )
        app._existing_available_targets = lambda: gui.VideoTextApp._existing_available_targets(app)
        return app

    def test_existing_results_start_requires_sources_and_output(self):
        app = self.make_existing_settings_app()
        app.existing_result_paths = []
        self.assertIsNone(gui.VideoTextApp._existing_results_settings(app))
        self.assertIn("at least one", app.existing_status.get())
        app.existing_result_paths = ["run"]
        app.existing_output_root.set("")
        self.assertIsNone(gui.VideoTextApp._existing_results_settings(app))
        self.assertIn("output folder", app.existing_status.get())

    def test_existing_dialog_local_provider_discards_only_unsupported_targets(self):
        app = self.make_existing_settings_app()
        app.existing_languages["en-CA"].set(True)
        app.existing_model_selector = Widget()
        app.existing_locale_summary = Variable("")
        with patch.object(gui, "TRANSLATION_TARGET_LOCALES", (
            ("en-CA", "English Canada"), ("pt-BR", "Portuguese Brazil"),
        )):
            gui.VideoTextApp._update_existing_provider_view(app)
        self.assertFalse(app.existing_languages["en-CA"].get())
        self.assertTrue(app.existing_languages["pt-BR"].get())
        self.assertEqual("disabled", app.existing_model_selector.options["state"])

    def test_existing_results_openai_settings_reuse_vetted_model_resolution(self):
        app = self.make_existing_settings_app(provider="openai")
        app.existing_languages["pt-BR"].set(False)
        app.existing_languages["en-CA"].set(True)
        with patch.object(gui, "resolve_vetted_openai_model", return_value="vetted-model") as resolve:
            settings = gui.VideoTextApp._existing_results_settings(app)

        resolve.assert_called_once_with("Recommended")
        self.assertEqual("vetted-model", settings[4])

    @staticmethod
    def preparation(valid=1, invalid=0, duplicates=0):
        presentation = Presentation()
        valid_items = tuple(
            ValidExistingResult(
                Path(f"run-{index}"), Path(f"run-{index}/cache/reading_order.pkl"),
                f"run-{index}", presentation, SimpleNamespace(),
            ) for index in range(valid)
        )
        return ExistingResultsTranslationPreparation(
            valid_items,
            tuple(InvalidExistingResult(Path(f"bad-{index}"), "Error", "invalid") for index in range(invalid)),
            tuple(DuplicateExistingResult(Path(f"dup-{index}"), Path("run-0"), Path("run-0/cache/reading_order.pkl")) for index in range(duplicates)),
            tuple(item.translation_source for item in valid_items),
            Path("workspace") if valid else None,
        )

    def make_prepared_handler_app(self):
        app = SimpleNamespace(
            existing_status=Variable(""), existing_results_dialog=object(), processing=True,
            existing_controls=[], existing_provider=Variable("openai"),
            existing_languages={}, existing_model_selector=Widget(),
        )
        app._existing_validation_summary = gui.VideoTextApp._existing_validation_summary
        app._finish_existing_results_translation = lambda: setattr(app, "processing", False)
        return app

    def test_zero_valid_stops_before_cloud_disclosure_or_provider(self):
        app = self.make_prepared_handler_app()
        with (
            patch.object(gui.messagebox, "showerror"),
            patch.object(gui.messagebox, "askokcancel") as disclosure,
            patch.object(gui, "OpenAITranslationProvider") as provider,
        ):
            gui.VideoTextApp._handle_existing_results_prepared(
                app, self.preparation(valid=0, invalid=1),
                ("openai", ("en-CA",), TranslationOutputGrouping.BY_SOURCE, ("excel",), "gpt-4.1-mini"),
            )
        disclosure.assert_not_called()
        provider.assert_not_called()
        self.assertFalse(app.processing)

    def test_declining_mixed_validation_stops_before_cloud_flow(self):
        app = self.make_prepared_handler_app()
        with (
            patch.object(gui.messagebox, "askyesno", return_value=False),
            patch.object(gui.messagebox, "askokcancel") as disclosure,
        ):
            gui.VideoTextApp._handle_existing_results_prepared(
                app, self.preparation(invalid=1, duplicates=1),
                ("openai", ("en-CA",), TranslationOutputGrouping.BY_SOURCE, ("excel",), "gpt-4.1-mini"),
            )
        disclosure.assert_not_called()
        self.assertFalse(app.processing)

    def test_accepting_mixed_validation_prompts_for_cloud_only_after_confirmation(self):
        app = self.make_prepared_handler_app()
        events = []
        app._run_existing_results_worker = lambda *_args: events.append("worker")
        with (
            patch.object(gui.messagebox, "askyesno", side_effect=lambda *_args, **_kwargs: events.append("validated") or True),
            patch.object(gui.messagebox, "askokcancel", side_effect=lambda *_args, **_kwargs: events.append("disclosure") or True),
            patch.object(gui.simpledialog, "askstring", return_value="test-key"),
            patch.object(gui.threading, "Thread") as thread_class,
        ):
            thread_class.return_value.start.side_effect = lambda: events.append("worker-started")
            gui.VideoTextApp._handle_existing_results_prepared(
                app, self.preparation(invalid=1),
                ("openai", ("en-CA",), TranslationOutputGrouping.BY_SOURCE, ("excel",), "gpt-4.1-mini"),
            )
        self.assertEqual(["validated", "disclosure", "worker-started"], events)

    def test_existing_results_worker_delegates_without_video_or_ocr_processing(self):
        app = SimpleNamespace(message_queue=queue.Queue(), local_translation_model_root=Path.cwd())
        preparation = self.preparation()
        with (
            patch.object(gui, "LocalCTranslate2Provider") as provider_class,
            patch.object(gui, "run_existing_results_translation", return_value="translated") as run_service,
            patch.object(gui, "process_request") as process,
        ):
            gui.VideoTextApp._run_existing_results_worker(
                app, preparation, "local", ("pt-BR",),
                TranslationOutputGrouping.BY_SOURCE, ("excel",), None, None,
            )
        process.assert_not_called()
        run_service.assert_called_once()
        self.assertEqual("existing_results_progress", app.message_queue.get_nowait()[0])
        self.assertEqual("existing_results_complete", app.message_queue.get_nowait()[0])

    def test_existing_results_completion_reports_partial_failure_and_all_selection_counts(self):
        app = SimpleNamespace(
            existing_status=Variable(""), existing_results_dialog=object(),
        )
        preparation = self.preparation(valid=1, invalid=1, duplicates=1)
        result = SimpleNamespace(
            job=SimpleNamespace(target_languages=("pt-BR",)),
            export_result=SimpleNamespace(
                success_count=3, failure_count=1,
                paths={"excel": (Path("workspace/translations/review.xlsx"),)},
            ),
            review_recommended_count=2,
        )
        with (
            patch.object(gui, "translation_locale_display_name", return_value="Portuguese — Brazil"),
            patch.object(app, "_show_existing_results_summary_dialog", create=True) as show,
        ):
            gui.VideoTextApp._show_existing_results_completion(app, preparation, result)

        summary = show.call_args.args[0]
        self.assertIn("Valid completed runs processed: 1", summary)
        self.assertIn("Invalid selections: 1", summary)
        self.assertIn("Duplicates ignored: 1", summary)
        self.assertIn("Succeeded: 3", summary)
        self.assertIn("Failed: 1", summary)
        self.assertIn("Review Recommended: 2", summary)
        self.assertIn("review.xlsx", summary)
        self.assertEqual("Translation completed with failures.", app.existing_status.get())

    def test_locale_arrow_navigation_wraps_selectable_controls(self):
        self.assertEqual(2, gui._next_locale_control_index(0, 3, -1))
        self.assertEqual(0, gui._next_locale_control_index(2, 3, 1))
        with self.assertRaises(ValueError):
            gui._next_locale_control_index(0, 0, 1)

    def make_configuration_app(self, mode="single", provider="local"):
        app = SimpleNamespace(
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
        app._available_translation_targets = lambda: gui.VideoTextApp._available_translation_targets(app)
        return app

    def make_provider_switch_app(self, provider="openai", **selected):
        languages = {
            "en-CA": Variable(selected.get("en-CA", False)),
            "pt-BR": Variable(selected.get("pt-BR", False)),
            "es-419": Variable(selected.get("es-419", False)),
        }
        app = SimpleNamespace(
            translation_provider=Variable(provider),
            translation_languages=languages,
            translation_enabled=Variable(True),
            translation_model_selector=Widget(),
            translation_provider_detail=Widget(),
            translation_locale_summary=Variable(""),
            local_translation_availability=SimpleNamespace(
                installed_pairs=(("en", "pt-BR"), ("en", "es-419")),
            ),
        )
        app._available_translation_targets = lambda: gui.VideoTextApp._available_translation_targets(app)
        app._discard_unavailable_translation_targets = lambda: gui.VideoTextApp._discard_unavailable_translation_targets(app)
        app._update_translation_summary = lambda: gui.VideoTextApp._update_translation_summary(app)
        return app

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

    def test_switching_openai_english_canada_to_local_deselects_it(self):
        app = self.make_provider_switch_app(**{"en-CA": True})

        app.translation_provider.set("local")
        with patch.object(gui, "TRANSLATION_TARGET_LOCALES", (
            ("en-CA", "English — Canada"),
            ("pt-BR", "Portuguese — Brazil"),
            ("es-419", "Spanish — Latin America"),
        )):
            gui.VideoTextApp._update_translation_provider_view(app)

        self.assertFalse(app.translation_languages["en-CA"].get())
        self.assertEqual("disabled", app.translation_model_selector.options["state"])
        self.assertEqual("Choose target locales…", app.translation_locale_summary.get())

    def test_switching_to_local_preserves_supported_selection(self):
        app = self.make_provider_switch_app(**{"en-CA": True, "pt-BR": True})

        app.translation_provider.set("local")
        gui.VideoTextApp._discard_unavailable_translation_targets(app)

        self.assertFalse(app.translation_languages["en-CA"].get())
        self.assertTrue(app.translation_languages["pt-BR"].get())

    def test_switching_back_to_openai_restores_availability_without_reselection(self):
        app = self.make_provider_switch_app(**{"en-CA": True, "pt-BR": True})
        app.translation_provider.set("local")
        gui.VideoTextApp._discard_unavailable_translation_targets(app)

        app.translation_provider.set("openai")
        discarded = gui.VideoTextApp._discard_unavailable_translation_targets(app)

        self.assertEqual((), discarded)
        self.assertIn("en-CA", gui.VideoTextApp._available_translation_targets(app))
        self.assertFalse(app.translation_languages["en-CA"].get())
        self.assertTrue(app.translation_languages["pt-BR"].get())

    def test_unavailable_local_target_cannot_reach_configuration(self):
        statuses = []
        app = self.make_configuration_app(provider="local")
        app.translation_languages = {"en-CA": Variable(True), "pt-BR": Variable(False)}
        app._set_status = statuses.append

        configuration = gui.VideoTextApp._translation_configuration(app)

        self.assertFalse(configuration)
        self.assertEqual("Selected target language is unavailable for this translation provider.", statuses[-1])

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
