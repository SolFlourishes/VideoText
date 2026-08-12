"""Focused immutable job-scope tests for translation output planning."""

from __future__ import annotations

from dataclasses import FrozenInstanceError
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from translation_job import TranslationJob, TranslationOutputGrouping, TranslationOutputPlan, TranslationSourceItem


def item(identifier: str = "video-a", name: str = "Video A", index: int = 0) -> TranslationSourceItem:
    return TranslationSourceItem(identifier, name, f"project:{identifier}", index)


class TranslationJobTests(unittest.TestCase):
    def test_valid_job_preserves_caller_order_and_normalizes_provider(self) -> None:
        job = TranslationJob("job-1", (item("b", "Video B", 1), item("a", "Video A", 0)), "en", ("es", "de"), " OpenAI ", TranslationOutputPlan(TranslationOutputGrouping.COMBINED))
        self.assertEqual(("b", "a"), tuple(value.source_item_id for value in job.source_items))
        self.assertEqual(("es", "de"), job.target_languages)
        self.assertEqual("openai", job.provider_name)

    def test_validation_rejects_empty_duplicates_and_source_target_match(self) -> None:
        plan = TranslationOutputPlan(TranslationOutputGrouping.BY_SOURCE)
        with self.assertRaisesRegex(ValueError, "job_id"):
            TranslationJob(" ", (item(),), "en", ("es",), "argos", plan)
        with self.assertRaisesRegex(ValueError, "source_items"):
            TranslationJob("job", (), "en", ("es",), "argos", plan)
        with self.assertRaisesRegex(ValueError, "immutable tuple"):
            TranslationJob("job", [item()], "en", ("es",), "argos", plan)  # type: ignore[arg-type]
        with self.assertRaisesRegex(ValueError, "unique source"):
            TranslationJob("job", (item(), item("VIDEO-A", "Other", 1)), "en", ("es",), "argos", plan)
        with self.assertRaisesRegex(ValueError, "unique after"):
            TranslationJob("job", (item(),), "en", ("es", "ES"), "argos", plan)
        with self.assertRaisesRegex(ValueError, "immutable tuple"):
            TranslationJob("job", (item(),), "en", ["es"], "argos", plan)  # type: ignore[arg-type]
        with self.assertRaisesRegex(ValueError, "must differ"):
            TranslationJob("job", (item(),), "en", ("en",), "argos", plan)

    def test_regional_variants_and_immutability_are_preserved(self) -> None:
        source = item()
        job = TranslationJob("job", (source,), "en", ("es", "es-MX"), "argos", TranslationOutputPlan(TranslationOutputGrouping.SEPARATE), {"scope": "test"})
        self.assertEqual(("es", "es-MX"), job.target_languages)
        with self.assertRaises(FrozenInstanceError):
            source.display_name = "Changed"
        with self.assertRaises(TypeError):
            job.metadata["scope"] = "changed"
