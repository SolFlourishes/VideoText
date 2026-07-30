"""Focused tests for paragraph canonical selection."""

import sys
from pathlib import Path
import unittest


sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from models import TextParagraph, TextType
from slide_consolidator import ParagraphCluster


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


if __name__ == "__main__":
    unittest.main()
