"""Focused deterministic tests for Translation Review Intelligence."""

from __future__ import annotations

from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from translation_contract import (TranslationProvenance, TranslationRequest,
    TranslationResult, TranslationSourceType, TranslationStatus)
from translation_review import (ASSESSMENT_REVISION, HumanTranslationReview,
    HumanTranslationReviewStatus, TranslationReviewStatus,
    TranslationReviewWarningCode, assess_translation_result,
    human_review_status_display, resolve_reviewed_translation)


def result(source: str, translated: str | None, *, failed: bool = False) -> TranslationResult:
    request = TranslationRequest("review-request", source, "en", "es",
        TranslationProvenance("video:slide:1:paragraph:0", TranslationSourceType.OCR))
    if failed:
        return TranslationResult(request, TranslationStatus.FAILURE, "fake", error="provider unavailable")
    return TranslationResult(request, TranslationStatus.SUCCESS, "fake", translated)


class TranslationReviewTests(unittest.TestCase):
    def test_reviewed_translation_resolution_covers_every_human_state(self) -> None:
        ai_text = "Traducción de IA original"
        provider_result = result("Source OCR remains exact", ai_text)
        cases = (
            (HumanTranslationReviewStatus.UNREVIEWED, None, ai_text, False),
            (HumanTranslationReviewStatus.ACCEPTED, None, ai_text, True),
            (HumanTranslationReviewStatus.EDITED_VERIFIED, "Traducción humana", "Traducción humana", True),
            (HumanTranslationReviewStatus.FLAGGED, None, ai_text, False),
        )
        for status, verified_text, expected_text, expected_verified in cases:
            with self.subTest(status=status):
                review = HumanTranslationReview("review-request", status, verified_text)
                resolution = resolve_reviewed_translation(
                    provider_result.status, provider_result.translated_text, review)
                self.assertEqual(expected_text, resolution.output_text)
                self.assertEqual(expected_verified, resolution.human_verified)
                self.assertEqual(status, resolution.human_review_status)
                self.assertEqual("Source OCR remains exact", provider_result.source_text)
                self.assertEqual(ai_text, provider_result.translated_text)

    def test_failed_translation_cannot_be_promoted_by_review_metadata(self) -> None:
        review = HumanTranslationReview(
            "review-request", HumanTranslationReviewStatus.EDITED_VERIFIED,
            "Human text attached to a failed provider result")
        resolution = resolve_reviewed_translation(TranslationStatus.FAILURE, None, review)
        self.assertIsNone(resolution.output_text)
        self.assertFalse(resolution.human_verified)
        self.assertEqual(TranslationStatus.FAILURE, resolution.translation_status)

    def test_human_review_states_are_separate_immutable_evidence(self) -> None:
        expected = {
            HumanTranslationReviewStatus.UNREVIEWED: "Unreviewed",
            HumanTranslationReviewStatus.ACCEPTED: "Accepted",
            HumanTranslationReviewStatus.EDITED_VERIFIED: "Edited / Verified",
            HumanTranslationReviewStatus.FLAGGED: "Flagged",
        }
        for status, label in expected.items():
            review = HumanTranslationReview(
                "review-request", status,
                "Traducción humana" if status is HumanTranslationReviewStatus.EDITED_VERIFIED else None,
            )
            self.assertEqual(label, human_review_status_display(review.status))
        with self.assertRaises(AttributeError):
            review.status = HumanTranslationReviewStatus.ACCEPTED

    def test_only_edited_verified_review_stores_separate_human_text(self) -> None:
        with self.assertRaisesRegex(ValueError, "require verified_translation"):
            HumanTranslationReview("review-request", HumanTranslationReviewStatus.EDITED_VERIFIED)
        with self.assertRaisesRegex(ValueError, "only valid"):
            HumanTranslationReview(
                "review-request", HumanTranslationReviewStatus.ACCEPTED, "Replacement text")
        review = HumanTranslationReview(
            "review-request", HumanTranslationReviewStatus.FLAGGED,
            reviewer_notes="Needs subject-matter review")
        self.assertEqual("Needs subject-matter review", review.reviewer_notes)
        with self.assertRaisesRegex(ValueError, "reviewer_notes"):
            HumanTranslationReview("review-request", reviewer_notes=3)

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
