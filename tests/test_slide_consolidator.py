"""Focused tests for paragraph canonical selection."""

import sys
from pathlib import Path
import unittest

import numpy as np


sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from models import CandidateFrame, OCRResult, TextLine, TextParagraph, TextType
from ocr_promotion_assessment import OCRPromotionDisposition, OCRPromotionReason
from slide_consolidator import ParagraphCluster, consolidate_slides


def build_cluster(variants: list[str]) -> ParagraphCluster:
    cluster = ParagraphCluster(
        TextParagraph(variants[0], text_type=TextType.BODY)
    )

    for text in variants[1:]:
        cluster.add(TextParagraph(text, text_type=TextType.BODY))

    return cluster


class ParagraphClusterSelectionTests(unittest.TestCase):
    def test_progressive_prefix_chain_selects_full_endpoint(self):
        short = "7. Consider various levels of integration"
        medium = (
            short
            + " The religiousness or spirituality of client"
            + " The desire of the client to integrate spirituality"
        )
        full = medium + " The nature of presenting problem"

        cluster = build_cluster([short] * 5 + [medium, full])

        self.assertEqual(cluster.best.text, full)
        self.assertIs(cluster.best, cluster.paragraphs[-1])

    def test_ocr_alternatives_keep_frequency_selection(self):
        cluster = build_cluster(
            ["based"] * 5 + ["basec", "s basec"]
        )

        self.assertEqual(cluster.best.text, "based")

    def test_exact_duplicates_keep_first_original_object(self):
        cluster = build_cluster([
            "Original text",
            " original   text ",
            "ORIGINAL TEXT",
        ])

        self.assertEqual(cluster.best.text, "Original text")
        self.assertIs(cluster.best, cluster.paragraphs[0])

    def test_unrelated_variants_keep_count_first_selection(self):
        cluster = build_cluster([
            "common text",
            "common text",
            "a much longer unrelated paragraph variant",
        ])

        self.assertEqual(cluster.best.text, "common text")


def promotion_frame(
    text: str,
    *,
    confidence: float = 0.65,
    box=(10, 10, 30, 20),
    frame_number: int = 1,
) -> CandidateFrame:
    line = TextLine(text, box[1], box[3], box[0], box[2], confidence, TextType.BODY)
    paragraph = TextParagraph(text, [line], TextType.BODY)
    result = OCRResult(text, confidence, np.array(box, dtype=float))
    return CandidateFrame(
        frame_number=frame_number,
        timestamp=float(frame_number),
        image=np.zeros((1080, 1920, 3), dtype=np.uint8),
        difference_score=0.0,
        ocr_results=[result],
        text_lines=[line],
        text_paragraphs=[paragraph],
        raw_ocr_results=[result],
    )


class ParagraphPromotionIntegrationTests(unittest.TestCase):
    def test_weak_fragments_are_withheld_without_mutating_source_evidence(self):
        for text in ("VI M", "V", "M M"):
            with self.subTest(text=text):
                source = promotion_frame(text)
                raw_object = source.raw_ocr_results[0]
                raw_box = raw_object.bounding_box.copy()

                slide = consolidate_slides([source])[0]

                self.assertEqual(slide.paragraphs, [])
                self.assertEqual(len(slide.promotion_records), 1)
                record = slide.promotion_records[0]
                self.assertFalse(record.included_in_presentation)
                self.assertEqual(
                    record.assessment.disposition,
                    OCRPromotionDisposition.NOT_PROMOTED_FRAGMENT,
                )
                self.assertIn(
                    OCRPromotionReason.FRAGMENT_LIKE_STRUCTURE,
                    record.assessment.reasons,
                )
                self.assertIs(source.raw_ocr_results[0], raw_object)
                self.assertEqual(source.raw_ocr_results[0].text, text)
                np.testing.assert_array_equal(raw_object.bounding_box, raw_box)

    def test_protected_compact_content_remains_in_presentation(self):
        for text in ("AI", "Q1", "x", "H2O", "2020", "2021", "42%", "54%", "8%", "5 mg"):
            with self.subTest(text=text):
                slide = consolidate_slides([promotion_frame(text)])[0]
                self.assertEqual([paragraph.text for paragraph in slide.paragraphs], [text])
                self.assertTrue(slide.promotion_records[0].included_in_presentation)

    def test_strong_or_corroborated_substantial_v_remains(self):
        strong = consolidate_slides([
            promotion_frame("V", confidence=0.98),
        ])[0]
        corroborated = consolidate_slides([
            promotion_frame("V", box=(0, 0, 600, 400), frame_number=1),
            promotion_frame("V", box=(0, 0, 600, 400), frame_number=2),
        ])[0]

        self.assertEqual([paragraph.text for paragraph in strong.paragraphs], ["V"])
        self.assertEqual([paragraph.text for paragraph in corroborated.paragraphs], ["V"])
        self.assertEqual(corroborated.promotion_records[0].context.observation_count, 2)

    def test_script_mismatch_and_latin_gibberish_remain_promoted(self):
        hebrew = consolidate_slides([promotion_frame("שלום")])[0]
        gibberish = consolidate_slides([
            promotion_frame("TONULSUGNLEE ECLGREINC NUL CLN", confidence=0.95),
        ])[0]

        self.assertEqual([paragraph.text for paragraph in hebrew.paragraphs], ["שלום"])
        self.assertEqual(
            hebrew.promotion_records[0].assessment.disposition,
            OCRPromotionDisposition.PROMOTED_REVIEW_RECOMMENDED,
        )
        self.assertIn(
            OCRPromotionReason.SCRIPT_MISMATCH,
            hebrew.promotion_records[0].assessment.reasons,
        )
        self.assertEqual(
            [paragraph.text for paragraph in gibberish.paragraphs],
            ["TONULSUGNLEE ECLGREINC NUL CLN"],
        )

    def test_missing_context_preserves_legacy_paragraph(self):
        source = CandidateFrame(
            frame_number=1,
            timestamp=0.0,
            image=None,
            difference_score=0.0,
            text_paragraphs=[TextParagraph("V", text_type=TextType.BODY)],
        )

        slide = consolidate_slides([source])[0]

        self.assertEqual([paragraph.text for paragraph in slide.paragraphs], ["V"])
        self.assertIsNone(slide.promotion_records[0].context.confidence)
        self.assertIsNone(slide.promotion_records[0].context.frame_dimensions)


if __name__ == "__main__":
    unittest.main()
