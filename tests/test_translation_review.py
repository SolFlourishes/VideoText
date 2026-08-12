"""Focused deterministic tests for Translation Review Intelligence."""

from __future__ import annotations

from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from translation_contract import (TranslationProvenance, TranslationRequest,
    TranslationResult, TranslationSourceType, TranslationStatus)
from translation_review import (ASSESSMENT_REVISION, TranslationReviewStatus,
    TranslationReviewWarningCode, assess_translation_result)


def result(source: str, translated: str | None, *, failed: bool = False) -> TranslationResult:
    request = TranslationRequest("review-request", source, "en", "es",
        TranslationProvenance("video:slide:1:paragraph:0", TranslationSourceType.OCR))
    if failed:
        return TranslationResult(request, TranslationStatus.FAILURE, "fake", error="provider unavailable")
    return TranslationResult(request, TranslationStatus.SUCCESS, "fake", translated)


class TranslationReviewTests(unittest.TestCase):
    def test_normal_success_has_no_claim_of_verification(self) -> None:
        assessment = assess_translation_result(result("A useful source sentence for people.", "Una oración útil para las personas."))
        self.assertEqual(TranslationReviewStatus.NORMAL_REVIEW, assessment.status)
        self.assertEqual((), assessment.warnings)
        self.assertEqual(ASSESSMENT_REVISION, assessment.revision)

    def test_failure_is_a_single_explicit_warning(self) -> None:
        assessment = assess_translation_result(result("Source text", None, failed=True))
        self.assertEqual(TranslationReviewStatus.TRANSLATION_FAILED, assessment.status)
        self.assertEqual((TranslationReviewWarningCode.TRANSLATION_FAILED,), tuple(item.code for item in assessment.warnings))

    def test_source_copy_similarity_is_conservative_and_deterministic(self) -> None:
        assessment = assess_translation_result(result(
            "This is a substantial source sentence for review.",
            "This is a substantial source sentence for review."))
        self.assertEqual(TranslationReviewStatus.REVIEW_RECOMMENDED, assessment.status)
        self.assertIn(TranslationReviewWarningCode.SOURCE_COPY_SIMILARITY, tuple(item.code for item in assessment.warnings))
        self.assertEqual(assessment, assess_translation_result(result(
            "This is a substantial source sentence for review.",
            "This is a substantial source sentence for review.")))
        similar = assess_translation_result(result(
            "This is a substantial source sentence for review.",
            "This is a substantial source sentence for reviews."))
        self.assertIn(TranslationReviewWarningCode.SOURCE_COPY_SIMILARITY,
                      tuple(item.code for item in similar.warnings))
        self.assertEqual(TranslationReviewStatus.NORMAL_REVIEW, assess_translation_result(result("OpenAI", "OpenAI")).status)
        self.assertEqual(TranslationReviewStatus.NORMAL_REVIEW, assess_translation_result(result("NASA", "NASA")).status)
        self.assertEqual(TranslationReviewStatus.NORMAL_REVIEW, assess_translation_result(result("2026", "2026")).status)

    def test_numeric_and_structure_signals_preserve_translation_evidence(self) -> None:
        source = "- 25 mg\n- 2026\n- final item"
        translated = "- 100 mg"
        assessment = assess_translation_result(result(source, translated))
        self.assertEqual(TranslationReviewStatus.REVIEW_RECOMMENDED, assessment.status)
        self.assertEqual((TranslationReviewWarningCode.NUMERIC_MISMATCH,
                          TranslationReviewWarningCode.STRUCTURE_MISMATCH),
                         tuple(item.code for item in assessment.warnings))
        self.assertEqual(TranslationReviewStatus.NORMAL_REVIEW,
            assess_translation_result(result(source, "- 25 mg\n- 2026\n- elemento final")).status)

    def test_assessment_and_context_are_immutable(self) -> None:
        assessment = assess_translation_result(result("There are 25 items in this detailed source.", "Hay 24 elementos en esta fuente detallada."))
        with self.assertRaises(AttributeError):
            assessment.status = TranslationReviewStatus.NORMAL_REVIEW
        with self.assertRaises(TypeError):
            assessment.warnings[0].context["source_numbers"] = ()
