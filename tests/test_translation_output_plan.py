"""Focused deterministic tests for pure translation workbook placement."""

from __future__ import annotations

from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from translation_job import TranslationJob, TranslationOutputGrouping, TranslationOutputPlan, TranslationSourceItem
from translation_output_plan import (
    language_display_name,
    plan_translation_output,
    sanitize_filename_label,
)


def job(grouping: TranslationOutputGrouping, sources=("Video A", "Video B"), languages=("es", "de"), batch_name=None) -> TranslationJob:
    items = tuple(TranslationSourceItem(f"video-{index}", name, f"project:{index}", index) for index, name in enumerate(sources))
    return TranslationJob("batch-1", items, "en", tuple(languages), "argos", TranslationOutputPlan(grouping, batch_name=batch_name))


class TranslationOutputPlanTests(unittest.TestCase):
    def test_by_language_creates_ordered_language_workbooks(self) -> None:
        layout = plan_translation_output(job(TranslationOutputGrouping.BY_LANGUAGE, languages=("es",)))
        self.assertEqual(("Spanish.xlsx",), tuple(book.filename for book in layout.workbooks))
        self.assertEqual(("Video A", "Video B"), tuple(sheet.name for sheet in layout.workbooks[0].sheets))

    def test_by_source_creates_ordered_language_sheets(self) -> None:
        layout = plan_translation_output(job(TranslationOutputGrouping.BY_SOURCE, sources=("Video A",), languages=("es", "de", "fr")))
        self.assertEqual("Video A.xlsx", layout.workbooks[0].filename)
        self.assertEqual(("Spanish", "German", "French"), tuple(sheet.name for sheet in layout.workbooks[0].sheets))

    def test_combined_and_separate_have_stable_ids_and_source_major_order(self) -> None:
        combined = plan_translation_output(job(TranslationOutputGrouping.COMBINED))
        self.assertEqual("batch-1:workbook:combined", combined.workbooks[0].workbook_id)
        self.assertEqual(("batch-1:sheet:video-0:es", "batch-1:sheet:video-0:de", "batch-1:sheet:video-1:es", "batch-1:sheet:video-1:de"), tuple(sheet.sheet_id for sheet in combined.workbooks[0].sheets))
        separate = plan_translation_output(job(TranslationOutputGrouping.SEPARATE))
        self.assertEqual(4, len(separate.workbooks))
        self.assertTrue(all(len(book.sheets) == 1 for book in separate.workbooks))

    def test_sanitization_collisions_and_limits_are_deterministic(self) -> None:
        layout = plan_translation_output(job(TranslationOutputGrouping.BY_LANGUAGE, sources=("A/B", "a:b", "x" * 50), languages=("es",)))
        names = tuple(sheet.name for sheet in layout.workbooks[0].sheets)
        self.assertEqual(("A B", "a b (2)", "x" * 31), names)
        self.assertEqual(layout, plan_translation_output(job(TranslationOutputGrouping.BY_LANGUAGE, sources=("A/B", "a:b", "x" * 50), languages=("es",))))
        self.assertEqual("zz-ZZ", language_display_name("zz-ZZ"))

    def test_planning_has_no_provider_or_filesystem_side_effects(self) -> None:
        planned = plan_translation_output(job(TranslationOutputGrouping.SEPARATE))
        self.assertEqual("batch-1", planned.job_id)
        self.assertEqual("batch-1:workbook:source:video-0:language:es", planned.workbooks[0].workbook_id)

    def test_optional_batch_name_prefixes_every_grouping_without_changing_blank_names(self) -> None:
        cases = {
            TranslationOutputGrouping.BY_LANGUAGE: (
                "Mod 2 - Spanish.xlsx", "Mod 2 - German.xlsx",
            ),
            TranslationOutputGrouping.BY_SOURCE: (
                "Mod 2 - Video A.xlsx", "Mod 2 - Video B.xlsx",
            ),
            TranslationOutputGrouping.COMBINED: (
                "Mod 2 - Translation Batch.xlsx",
            ),
            TranslationOutputGrouping.SEPARATE: (
                "Mod 2 - Video A - Spanish.xlsx",
                "Mod 2 - Video A - German.xlsx",
                "Mod 2 - Video B - Spanish.xlsx",
                "Mod 2 - Video B - German.xlsx",
            ),
        }
        for grouping, expected in cases.items():
            with self.subTest(grouping=grouping):
                labeled = plan_translation_output(job(grouping, batch_name="Mod 2"))
                blank = plan_translation_output(job(grouping, batch_name="  "))
                original = plan_translation_output(job(grouping))
                self.assertEqual(expected, tuple(book.filename for book in labeled.workbooks))
                self.assertEqual(
                    tuple(book.filename for book in original.workbooks),
                    tuple(book.filename for book in blank.workbooks),
                )

    def test_batch_name_sanitization_is_windows_safe_and_can_be_empty(self) -> None:
        self.assertEqual("Mod 2", sanitize_filename_label(' Mod<2>:"/\\|?*... '))
        self.assertIsNone(sanitize_filename_label('<>:"/\\|?*... '))
        self.assertEqual("CON Translation", sanitize_filename_label("CON"))
