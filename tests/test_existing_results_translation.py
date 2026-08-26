"""Focused tests for headless existing-results translation preparation."""

from __future__ import annotations

from contextlib import ExitStack
import csv
from pathlib import Path
import pickle
import sys
import tempfile
import unittest
from unittest.mock import patch


sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import existing_results_translation
import processing_service
from existing_results_translation import (
    ExistingResultsTranslationPreparation,
    prepare_existing_results_translation,
    run_existing_results_translation,
)
from models import CandidateFrame, TextParagraph, TextType
from translation_contract import TranslationResult, TranslationStatus
from translation_job import TranslationOutputGrouping
from translation_review import TranslationReviewStatus


class FakeProvider:
    provider_id = "fake-existing-results"

    def __init__(self, fail_source: str | None = None, copy_source: str | None = None):
        self.fail_source = fail_source
        self.copy_source = copy_source
        self.failure_emitted = False
        self.requests = []

    def translate(self, request):
        self.requests.append(request)
        if request.source_text == self.fail_source and not self.failure_emitted:
            self.failure_emitted = True
            return TranslationResult(
                request, TranslationStatus.FAILURE, self.provider_id,
                model_id="fake-model-v1", error="simulated provider failure",
            )
        translated = (
            request.source_text
            if request.source_text == self.copy_source
            else "Contenido traducido claramente para revisión humana."
        )
        return TranslationResult(
            request, TranslationStatus.SUCCESS, self.provider_id,
            translated, model_id="fake-model-v1",
        )


class ExistingResultsTranslationTests(unittest.TestCase):
    def setUp(self):
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary_directory.cleanup)
        self.root = Path(self.temporary_directory.name)

    def completed_run(self, name: str, text: str = "Preserved text") -> Path:
        run = self.root / "completed" / name
        checkpoint = run / "cache" / "reading_order.pkl"
        checkpoint.parent.mkdir(parents=True)
        frame = CandidateFrame(
            frame_number=1,
            timestamp=1.0,
            image=None,
            difference_score=0.0,
            text_paragraphs=[TextParagraph(text, text_type=TextType.BODY)],
        )
        with checkpoint.open("wb") as file:
            pickle.dump([frame], file)
        return run

    def test_two_valid_results_preserve_order_and_prepare_translation_sources(self):
        first = self.completed_run("First Run", "First paragraph")
        second = self.completed_run("Second Run", "Second paragraph")

        result = prepare_existing_results_translation(
            (first, second), self.root / "translations"
        )

        self.assertTrue(result.has_valid_sources)
        self.assertEqual((first, second), tuple(item.selected_path for item in result.valid_results))
        self.assertEqual(("First Run", "Second Run"), tuple(item.source_name for item in result.valid_results))
        self.assertEqual(
            ("First paragraph", "Second paragraph"),
            tuple(source.presentation.slides[0].paragraphs[0].text for source in result.translation_sources),
        )
        self.assertEqual(
            ("existing-result-0", "existing-result-1"),
            tuple(source.source_item.source_item_id for source in result.translation_sources),
        )

    def test_same_run_twice_records_duplicate_and_retains_first(self):
        run = self.completed_run("Repeated")

        result = prepare_existing_results_translation(
            (run, run), self.root / "translations"
        )

        self.assertEqual(1, len(result.valid_results))
        self.assertEqual(1, len(result.duplicate_results))
        self.assertEqual(run, result.duplicate_results[0].duplicate_of)

    def test_run_directory_and_direct_checkpoint_deduplicate(self):
        run = self.completed_run("Directory And File")
        checkpoint = run / "cache" / "reading_order.pkl"

        result = prepare_existing_results_translation(
            (run, checkpoint), self.root / "translations"
        )

        self.assertEqual((run,), tuple(item.selected_path for item in result.valid_results))
        self.assertEqual(checkpoint, result.duplicate_results[0].resolved_checkpoint_path)
        self.assertEqual(checkpoint, result.valid_results[0].resolved_checkpoint_path)

    def test_missing_corrupted_and_incompatible_selections_are_recorded(self):
        missing = self.root / "completed" / "Missing"
        missing.mkdir(parents=True)
        corrupted = self.root / "completed" / "Corrupted" / "cache" / "reading_order.pkl"
        corrupted.parent.mkdir(parents=True)
        corrupted.write_bytes(b"not a pickle")
        incompatible = self.root / "completed" / "Incompatible" / "cache" / "reading_order.pkl"
        incompatible.parent.mkdir(parents=True)
        with incompatible.open("wb") as file:
            pickle.dump({"wrong": "shape"}, file)

        result = prepare_existing_results_translation(
            (missing, corrupted, incompatible), self.root / "unused-output"
        )

        self.assertFalse(result.has_valid_sources)
        self.assertEqual((), result.translation_sources)
        self.assertEqual(3, len(result.invalid_results))
        self.assertEqual(
            ("CheckpointValidationError", "CheckpointLoadError", "CheckpointLoadError"),
            tuple(item.error_type for item in result.invalid_results),
        )
        self.assertIsNone(result.output_workspace)
        self.assertFalse((self.root / "unused-output").exists())

    def test_mixed_valid_and_invalid_keeps_valid_source(self):
        valid = self.completed_run("Usable")
        missing = self.root / "completed" / "Missing"
        missing.mkdir()

        result = prepare_existing_results_translation(
            (missing, valid), self.root / "translations"
        )

        self.assertEqual((valid,), tuple(item.selected_path for item in result.valid_results))
        self.assertEqual((missing,), tuple(item.selected_path for item in result.invalid_results))
        self.assertEqual(1, len(result.translation_sources))

    def test_source_identity_uses_run_folder_and_preserves_checkpoint(self):
        run = self.completed_run("Evidence Name")
        (run / "misleading-name.md").write_text("neighbor", encoding="utf-8")
        checkpoint = run / "cache" / "reading_order.pkl"
        original_bytes = checkpoint.read_bytes()

        result = prepare_existing_results_translation(
            (checkpoint,), self.root / "translations"
        )

        item = result.valid_results[0]
        self.assertEqual("Evidence Name", item.source_name)
        self.assertEqual("Evidence Name", item.translation_source.source_item.display_name)
        self.assertEqual(checkpoint, item.resolved_checkpoint_path)
        self.assertIn(str(checkpoint), item.translation_source.source_item.evidence_reference)
        self.assertEqual(original_bytes, checkpoint.read_bytes())

    def test_output_workspace_suffixes_without_overwriting_existing_files(self):
        run = self.completed_run("Source")
        output_root = self.root / "translations"
        first = output_root / "translation-existing-results"
        second = output_root / "translation-existing-results_2"
        first.mkdir(parents=True)
        second.mkdir()
        marker = first / "keep.txt"
        marker.write_text("unchanged", encoding="utf-8")

        result = prepare_existing_results_translation((run,), output_root)

        self.assertEqual(output_root / "translation-existing-results_3", result.output_workspace)
        self.assertTrue(result.output_workspace.is_dir())
        self.assertEqual("unchanged", marker.read_text(encoding="utf-8"))
        self.assertFalse(result.output_workspace.is_relative_to(run))

    def test_output_workspace_is_rejected_inside_selected_source(self):
        run = self.completed_run("Protected Source")

        with self.assertRaisesRegex(ValueError, "must not be inside"):
            prepare_existing_results_translation((run,), run / "translations")

        self.assertFalse((run / "translations").exists())

    def test_service_uses_read_only_helper_and_never_invokes_processing(self):
        run = self.completed_run("No OCR")
        prohibited = (
            "process_request", "resolve_video_source", "open_video", "analyze_video",
            "perform_ocr", "reconstruct_reading_order", "create_replay_run_directory",
        )
        with ExitStack() as stack:
            for name in prohibited:
                stack.enter_context(
                    patch.object(processing_service, name, side_effect=AssertionError(name))
                )
            helper = stack.enter_context(patch.object(
                existing_results_translation,
                "reconstruct_presentation_from_reading_order",
                wraps=processing_service.reconstruct_presentation_from_reading_order,
            ))
            result = prepare_existing_results_translation(
                (run,), self.root / "translations"
            )

        helper.assert_called_once_with(run / "cache" / "reading_order.pkl")
        self.assertEqual(1, len(result.translation_sources))

    def test_orchestration_translates_two_sources_and_two_locales_in_existing_order(self):
        first = self.completed_run("First Source", "First source OCR remains exact.")
        second = self.completed_run("Second Source", "Second source OCR remains exact.")
        preparation = prepare_existing_results_translation(
            (first, second), self.root / "output"
        )
        provider = FakeProvider()
        progress = []

        result = run_existing_results_translation(
            preparation,
            "existing-batch",
            provider,
            ("es-419", "fr"),
            TranslationOutputGrouping.COMBINED,
            ("csv",),
            progress_callback=lambda current, total: progress.append((current, total)),
        )

        self.assertEqual(
            ("First Source", "Second Source"),
            tuple(item.display_name for item in result.job.source_items),
        )
        self.assertEqual(("es-419", "fr"), result.job.target_languages)
        self.assertEqual(
            (
                ("First source OCR remains exact.", "es-419"),
                ("Second source OCR remains exact.", "es-419"),
                ("First source OCR remains exact.", "fr"),
                ("Second source OCR remains exact.", "fr"),
            ),
            tuple((request.source_text, request.target_language) for request in provider.requests),
        )
        self.assertEqual((4, 4), progress[-1])
        self.assertEqual(4, result.export_result.success_count)

    def test_orchestration_preserves_provider_model_locale_source_and_review_provenance(self):
        run = self.completed_run("Provenance", "Canonical source OCR text.")
        checkpoint = run / "cache" / "reading_order.pkl"
        preparation = prepare_existing_results_translation((run,), self.root / "output")
        provider = FakeProvider()

        result = run_existing_results_translation(
            preparation, "provenance-job", provider, ("ko-KR",),
            TranslationOutputGrouping.BY_SOURCE, ("csv",),
        )

        csv_path = result.export_result.paths["csv"][0]
        with csv_path.open(encoding="utf-8", newline="") as file:
            row = next(csv.DictReader(file))
        self.assertEqual("Canonical source OCR text.", row["Original Text"])
        self.assertEqual("ko-KR", row["Target Language"])
        self.assertEqual(provider.provider_id, row["Provider"])
        self.assertEqual("fake-model-v1", row["Model"])
        self.assertEqual("success", row["Translation Status"])
        self.assertEqual("Normal Review", row["Review Status"])
        self.assertEqual(checkpoint, preparation.valid_results[0].resolved_checkpoint_path)

    def test_orchestration_routes_normal_recommended_and_failed_through_existing_review(self):
        normal = self.completed_run("Normal", "Ordinary source material for translation.")
        copied_text = "This substantial source sentence should be flagged when copied exactly."
        copied = self.completed_run("Copied", copied_text)
        failed_text = "This source is configured to fail translation."
        failed = self.completed_run("Failed", failed_text)
        preparation = prepare_existing_results_translation(
            (normal, copied, failed), self.root / "output"
        )
        provider = FakeProvider(fail_source=failed_text, copy_source=copied_text)

        result = run_existing_results_translation(
            preparation, "review-job", provider, ("es-419",),
            TranslationOutputGrouping.BY_LANGUAGE, ("csv",),
        )

        self.assertEqual(
            (
                TranslationReviewStatus.NORMAL_REVIEW,
                TranslationReviewStatus.REVIEW_RECOMMENDED,
                TranslationReviewStatus.TRANSLATION_FAILED,
            ),
            tuple(assessment.status for assessment in result.assessments),
        )
        self.assertEqual(2, result.export_result.success_count)
        self.assertEqual(1, result.export_result.failure_count)
        self.assertEqual(3, len(provider.requests))

    def test_partial_failure_does_not_abort_later_sources_or_locales(self):
        failure_text = "Fail only this request."
        first = self.completed_run("Failure First", failure_text)
        second = self.completed_run("Success Later", "Continue after the failed request.")
        preparation = prepare_existing_results_translation(
            (first, second), self.root / "output"
        )
        provider = FakeProvider(fail_source=failure_text)

        result = run_existing_results_translation(
            preparation, "partial-job", provider, ("es-419", "fr"),
            TranslationOutputGrouping.COMBINED, ("csv", "markdown"),
        )

        self.assertEqual(4, len(provider.requests))
        self.assertEqual(3, result.export_result.success_count)
        self.assertEqual(1, result.export_result.failure_count)
        self.assertTrue(any(
            assessment.status is TranslationReviewStatus.TRANSLATION_FAILED
            for assessment in result.assessments
        ))
        for paths in result.export_result.paths.values():
            self.assertTrue(all(path.is_file() for path in paths))

    def test_all_grouping_modes_write_only_beneath_workflow_workspace(self):
        expected_workbooks = {
            TranslationOutputGrouping.BY_LANGUAGE: 2,
            TranslationOutputGrouping.BY_SOURCE: 2,
            TranslationOutputGrouping.COMBINED: 1,
            TranslationOutputGrouping.SEPARATE: 4,
        }
        for grouping, expected_count in expected_workbooks.items():
            with self.subTest(grouping=grouping):
                first = self.completed_run(f"{grouping.value} First", "First grouping text.")
                second = self.completed_run(f"{grouping.value} Second", "Second grouping text.")
                preparation = prepare_existing_results_translation(
                    (first, second), self.root / f"output-{grouping.value}"
                )

                result = run_existing_results_translation(
                    preparation, f"job-{grouping.value}", FakeProvider(),
                    ("es-419", "fr"), grouping, ("excel",),
                )

                paths = result.export_result.paths["excel"]
                self.assertEqual(grouping, result.job.output_plan.grouping)
                self.assertEqual(expected_count, len(paths))
                self.assertTrue(all(
                    path.is_relative_to(preparation.output_workspace / "translations")
                    for path in paths
                ))

    def test_orchestration_never_mutates_sources_or_invokes_processing(self):
        run = self.completed_run("Immutable", "Immutable source OCR.")
        checkpoint = run / "cache" / "reading_order.pkl"
        source_translations = run / "translations"
        source_translations.mkdir()
        marker = source_translations / "existing.txt"
        marker.write_text("unchanged", encoding="utf-8")
        original_bytes = checkpoint.read_bytes()
        source_paths_before = {path.relative_to(run) for path in run.rglob("*")}
        preparation = prepare_existing_results_translation((run,), self.root / "output")
        prohibited = (
            "process_request", "resolve_video_source", "open_video", "analyze_video",
            "perform_ocr", "reconstruct_reading_order", "create_replay_run_directory",
        )

        with ExitStack() as stack:
            for name in prohibited:
                stack.enter_context(
                    patch.object(processing_service, name, side_effect=AssertionError(name))
                )
            result = run_existing_results_translation(
                preparation, "immutable-job", FakeProvider(), ("fr",),
                TranslationOutputGrouping.BY_SOURCE, ("csv",),
            )

        self.assertEqual(original_bytes, checkpoint.read_bytes())
        self.assertEqual("unchanged", marker.read_text(encoding="utf-8"))
        self.assertEqual(source_paths_before, {path.relative_to(run) for path in run.rglob("*")})
        self.assertTrue(result.export_result.paths["csv"][0].is_relative_to(preparation.output_workspace))

    def test_orchestration_refuses_empty_preparation_and_reuses_locale_validation(self):
        empty = ExistingResultsTranslationPreparation((), (), (), (), None)
        with self.assertRaisesRegex(ValueError, "At least one valid"):
            run_existing_results_translation(
                empty, "empty", FakeProvider(), ("fr",),
                TranslationOutputGrouping.BY_SOURCE, ("csv",),
            )

        run = self.completed_run("Invalid Locale")
        preparation = prepare_existing_results_translation((run,), self.root / "output")
        with self.assertRaisesRegex(ValueError, "valid language identifier"):
            run_existing_results_translation(
                preparation, "invalid-locale", FakeProvider(), ("not a locale",),
                TranslationOutputGrouping.BY_SOURCE, ("csv",),
            )


if __name__ == "__main__":
    unittest.main()
