"""Focused tests for derived OCR promotion assessment foundations."""

from dataclasses import FrozenInstanceError
import unittest

from ocr_promotion_assessment import (
    CURRENT_OCR_RECOGNITION_PROFILE,
    OCRPromotionDisposition,
    OCRPromotionContext,
    OCRPromotionReason,
    OCRRecognitionProfile,
    UnicodeScript,
    assess_ocr_text,
    assess_ocr_promotion,
    is_protected_short_content,
    observe_scripts,
)


WEAK_FRAGMENT_FIXTURES = ("VI M", "V", "M M")
LATIN_GIBBERISH_FIXTURE = "TONULSUGNLEE ECLGREINC NUL CLN"
PROTECTED_SHORT_FIXTURES = ("AI", "Q1", "x", "H2O", "2021", "42%", "5 mg")


class ScriptObservationTests(unittest.TestCase):
    def test_required_scripts_are_observed(self):
        examples = {
            "Hello": UnicodeScript.LATIN,
            "שלום": UnicodeScript.HEBREW,
            "مرحبا": UnicodeScript.ARABIC,
            "Привет": UnicodeScript.CYRILLIC,
            "안녕": UnicodeScript.HANGUL,
            "漢字": UnicodeScript.HAN,
        }
        for text, expected in examples.items():
            with self.subTest(text=text):
                self.assertEqual(observe_scripts(text), frozenset({expected}))

    def test_digits_whitespace_and_punctuation_are_neutral(self):
        self.assertEqual(observe_scripts("2021 42% -- (5.0)"), frozenset())

    def test_mixed_scripts_are_all_represented(self):
        self.assertEqual(
            observe_scripts("Hello שלום"),
            frozenset({UnicodeScript.LATIN, UnicodeScript.HEBREW}),
        )


class PromotionAssessmentTests(unittest.TestCase):
    def test_hebrew_output_under_current_profile_recommends_review(self):
        assessment = assess_ocr_text("שלום")
        self.assertEqual(
            assessment.disposition,
            OCRPromotionDisposition.PROMOTED_REVIEW_RECOMMENDED,
        )
        self.assertEqual(assessment.reasons, (OCRPromotionReason.SCRIPT_MISMATCH,))
        self.assertEqual(assessment.observed_scripts, (UnicodeScript.HEBREW,))

    def test_latin_gibberish_is_only_observed_as_latin(self):
        assessment = assess_ocr_text(LATIN_GIBBERISH_FIXTURE)
        self.assertEqual(assessment.disposition, OCRPromotionDisposition.PROMOTED)
        self.assertEqual(assessment.observed_scripts, (UnicodeScript.LATIN,))
        self.assertNotIn(UnicodeScript.HEBREW, assessment.observed_scripts)

    def test_non_english_latin_text_is_not_a_script_mismatch(self):
        for text in ("Olá, ação", "Español", "Français"):
            with self.subTest(text=text):
                self.assertEqual(
                    assess_ocr_text(text).disposition,
                    OCRPromotionDisposition.PROMOTED,
                )

    def test_profile_is_configurable_without_language_assumptions(self):
        profile = OCRRecognitionProfile(
            name="Hebrew recognition",
            recognized_scripts=frozenset({UnicodeScript.HEBREW}),
        )
        self.assertEqual(
            assess_ocr_text("שלום", profile).disposition,
            OCRPromotionDisposition.PROMOTED,
        )

    def test_weak_fragment_regression_fixtures_are_not_suppressed_yet(self):
        for text in WEAK_FRAGMENT_FIXTURES:
            with self.subTest(text=text):
                self.assertEqual(
                    assess_ocr_text(text).disposition,
                    OCRPromotionDisposition.PROMOTED,
                )

    def test_assessments_and_profiles_are_immutable(self):
        assessment = assess_ocr_text("Hello")
        with self.assertRaises(FrozenInstanceError):
            assessment.disposition = OCRPromotionDisposition.NOT_PROMOTED_FRAGMENT
        with self.assertRaises(FrozenInstanceError):
            CURRENT_OCR_RECOGNITION_PROFILE.name = "changed"


class ProtectedShortContentTests(unittest.TestCase):
    def test_required_short_and_numeric_content_is_protected(self):
        for text in PROTECTED_SHORT_FIXTURES:
            with self.subTest(text=text):
                self.assertTrue(is_protected_short_content(text))
                self.assertTrue(assess_ocr_text(text).protected_short_content)

    def test_multi_token_alphabetic_fragments_are_not_shape_protected(self):
        self.assertFalse(is_protected_short_content("VI M"))
        self.assertFalse(is_protected_short_content("M M"))

    def test_long_or_empty_content_is_not_short_content(self):
        self.assertFalse(is_protected_short_content(""))
        self.assertFalse(is_protected_short_content("A legitimately long title"))


class ContextualFragmentAssessmentTests(unittest.TestCase):
    @staticmethod
    def weak_context(**overrides):
        values = {
            "confidence": 0.65,
            "region_count": 2,
            "bounding_box": (10, 10, 30, 20),
            "frame_dimensions": (1920, 1080),
            "observation_count": 1,
        }
        values.update(overrides)
        return OCRPromotionContext(**values)

    def test_multiple_weak_signals_can_suppress_fragment_shapes(self):
        expected_reasons = {
            OCRPromotionReason.FRAGMENT_LIKE_STRUCTURE,
            OCRPromotionReason.WEAK_OCR_EVIDENCE,
            OCRPromotionReason.TINY_VISUAL_FOOTPRINT,
            OCRPromotionReason.UNCORROBORATED_OBSERVATION,
        }
        for text in ("VI M", "M M", "V"):
            with self.subTest(text=text):
                assessment = assess_ocr_promotion(text, self.weak_context())
                self.assertEqual(
                    assessment.disposition,
                    OCRPromotionDisposition.NOT_PROMOTED_FRAGMENT,
                )
                self.assertEqual(set(assessment.reasons), expected_reasons)

    def test_shortness_alone_does_not_suppress(self):
        assessment = assess_ocr_promotion(
            "V",
            self.weak_context(confidence=0.98, bounding_box=(0, 0, 600, 400)),
        )
        self.assertEqual(assessment.disposition, OCRPromotionDisposition.PROMOTED)

    def test_low_confidence_alone_recommends_review_but_does_not_suppress(self):
        assessment = assess_ocr_promotion("ordinary text", self.weak_context())
        self.assertEqual(
            assessment.disposition,
            OCRPromotionDisposition.PROMOTED_REVIEW_RECOMMENDED,
        )
        self.assertIn(OCRPromotionReason.WEAK_OCR_EVIDENCE, assessment.reasons)

    def test_single_frame_appearance_alone_does_not_suppress(self):
        assessment = assess_ocr_promotion(
            "ordinary text",
            self.weak_context(confidence=0.98, bounding_box=(0, 0, 600, 400)),
        )
        self.assertEqual(assessment.disposition, OCRPromotionDisposition.PROMOTED)

    def test_tiny_footprint_alone_does_not_suppress(self):
        assessment = assess_ocr_promotion(
            "ordinary text",
            self.weak_context(confidence=0.98, observation_count=3),
        )
        self.assertEqual(assessment.disposition, OCRPromotionDisposition.PROMOTED)

    def test_corroborated_or_strong_fragment_is_preserved(self):
        strong = assess_ocr_promotion(
            "V",
            self.weak_context(confidence=0.99, observation_count=1),
        )
        corroborated = assess_ocr_promotion(
            "M M",
            self.weak_context(
                observation_count=3,
                bounding_box=(0, 0, 600, 400),
            ),
        )
        self.assertEqual(strong.disposition, OCRPromotionDisposition.PROMOTED)
        self.assertEqual(corroborated.disposition, OCRPromotionDisposition.PROMOTED_REVIEW_RECOMMENDED)

    def test_protected_short_and_chart_values_remain_promoted(self):
        for text in PROTECTED_SHORT_FIXTURES + ("2020", "54%", "8%"):
            with self.subTest(text=text):
                assessment = assess_ocr_promotion(text, self.weak_context())
                self.assertNotEqual(
                    assessment.disposition,
                    OCRPromotionDisposition.NOT_PROMOTED_FRAGMENT,
                )
                self.assertTrue(assessment.protected_short_content)

    def test_hebrew_script_mismatch_is_not_fragment_suppressed(self):
        assessment = assess_ocr_promotion("ש", self.weak_context())
        self.assertEqual(
            assessment.disposition,
            OCRPromotionDisposition.PROMOTED_REVIEW_RECOMMENDED,
        )
        self.assertIn(OCRPromotionReason.SCRIPT_MISMATCH, assessment.reasons)

    def test_language_neutral_and_nonlexical_behavior_is_preserved(self):
        for text in ("Olá, ação", LATIN_GIBBERISH_FIXTURE):
            with self.subTest(text=text):
                assessment = assess_ocr_promotion(
                    text,
                    self.weak_context(confidence=0.95),
                )
                self.assertEqual(
                    assessment.disposition,
                    OCRPromotionDisposition.PROMOTED,
                )

    def test_context_is_immutable_and_validated(self):
        context = self.weak_context()
        with self.assertRaises(FrozenInstanceError):
            context.confidence = 0.9
        with self.assertRaises(ValueError):
            OCRPromotionContext(confidence=1.1)
        with self.assertRaises(ValueError):
            OCRPromotionContext(observation_count=0)


if __name__ == "__main__":
    unittest.main()
