"""Focused OCR diagnostic export tests using synthetic images and regions."""

from pathlib import Path
from types import SimpleNamespace
import json
import sys
import tempfile
import unittest

import numpy as np


sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from models import CandidateFrame, OCRResult, TextLine, TextParagraph, TextType
from ocr_diagnostics import DiagnosticError, DiagnosticOptions, OCRDiagnosticsWriter
from slide_consolidator import consolidate_slides


def frame(frame_index=25):
    image = np.full((90, 140, 3), 255, dtype=np.uint8)
    results = [
        OCRResult("Heading", 0.95, np.array([80, 5, 130, 20])),
        OCRResult("Body", 0.70, np.array([5, 60, 40, 78])),
        OCRResult("中心", 0.85, np.array([50, 35, 85, 52])),
    ]
    return SimpleNamespace(
        frame_number=frame_index,
        timestamp=5.0,
        image=image,
        ocr_results=results,
        text_lines=[TextLine("Heading", 5, 20, 80, 130, 0.95)],
        text_paragraphs=[TextParagraph("Heading\nBody", text_type=TextType.BODY)],
    )


class OCRDiagnosticsTests(unittest.TestCase):
    def setUp(self):
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary_directory.cleanup)
        self.output = Path(self.temporary_directory.name) / "diagnostics"

    def writer(self, **kwargs):
        return OCRDiagnosticsWriter(DiagnosticOptions(
            output_directory=self.output,
            frame_indices=frozenset({25}),
            **kwargs,
        ), "synthetic.mp4")

    def test_disabled_diagnostics_have_no_output_until_writer_is_created_and_written(self):
        self.assertFalse(self.output.exists())

    def test_frame_exports_are_deterministic_and_preserve_unicode_and_orders(self):
        source = frame()
        writer = self.writer(low_confidence_threshold=0.80)
        writer.capture_ocr_frames([source])
        writer.capture_reconstructed_frames([source])
        writer.write()

        frame_directory = self.output / "frames" / "frame_000025"
        data = json.loads((frame_directory / "regions.json").read_text(encoding="utf-8"))
        self.assertTrue((frame_directory / "original.png").is_file())
        self.assertTrue((frame_directory / "ocr_input.png").is_file())
        self.assertTrue((frame_directory / "regions.png").is_file())
        self.assertTrue((frame_directory / "reading_order.png").is_file())
        self.assertEqual(data["original_ocr_sequence"], ["region_001", "region_002", "region_003"])
        self.assertEqual(data["reading_order_sequence"], ["region_001", "region_002", "region_003"])
        self.assertEqual(data["regions"][2]["recognized_text"], "中心")
        self.assertEqual(data["regions"][1]["flags"], ["low_confidence"])
        self.assertEqual(data["confidence_summary"]["below_threshold"], 1)
        self.assertEqual((frame_directory / "reconstructed_text.txt").read_text(encoding="utf-8"), "Heading\nBody")

    def test_missing_confidence_and_filtered_regions_are_explicit(self):
        source = frame()
        source.ocr_results[0].confidence = None
        writer = self.writer()
        writer.capture_ocr_frames([source])
        source.ocr_results = [source.ocr_results[1]]
        writer.capture_reconstructed_frames([source])
        region = writer.frames[25].regions[0]

        self.assertIn("confidence_unavailable", region.flags)
        self.assertIn("not_in_reading_order", region.flags)

    def test_reading_order_replay_reports_missing_raw_ocr_sequence(self):
        writer = self.writer()
        writer.capture_reconstructed_frames([frame()], raw_sequence_available=False)

        self.assertIn("Raw OCR sequence", writer.frames[25].warnings[0])
        self.assertIn("Raw OCR sequence", writer.run_warnings[0])

    def test_selected_filter_missing_frame_and_overwrite_behavior(self):
        writer = self.writer()
        writer.capture_ocr_frames([frame()])
        writer.capture_reconstructed_frames([frame()])
        writer.write()
        with self.assertRaisesRegex(DiagnosticError, "already exists"):
            writer.write()

        missing = OCRDiagnosticsWriter(DiagnosticOptions(
            output_directory=Path(self.temporary_directory.name) / "missing",
            frame_indices=frozenset({99}),
            strict=True,
        ), "synthetic.mp4")
        missing.capture_ocr_frames([frame()])
        with self.assertRaisesRegex(DiagnosticError, "not found"):
            missing.write()

    def test_slide_exports_and_relative_summary_links(self):
        source = frame()
        writer = OCRDiagnosticsWriter(DiagnosticOptions(
            output_directory=self.output,
            slide_numbers=frozenset({6}),
        ), "synthetic.mp4")
        writer.capture_ocr_frames([source])
        writer.capture_reconstructed_frames([source])
        slide = SimpleNamespace(
            slide_number=6,
            builds=[SimpleNamespace(candidate_frames=[source], final_text="Before consolidation")],
            paragraphs=[TextParagraph("Final consolidated", text_type=TextType.BODY)],
        )
        writer.capture_slides([slide])
        writer.write()

        self.assertTrue((self.output / "slides" / "slide_0006" / "slide.json").is_file())
        self.assertIn("frames/frame_000025/regions.json", (self.output / "summary.md").read_text(encoding="utf-8"))
        self.assertEqual(writer.frames[25].associated_slide_number, 6)

    def test_frame_selection_exports_only_its_associated_slide(self):
        source = frame()
        writer = self.writer()
        writer.capture_ocr_frames([source])
        writer.capture_reconstructed_frames([source])
        matching_slide = SimpleNamespace(
            slide_number=1,
            builds=[SimpleNamespace(candidate_frames=[source], final_text="One")],
            paragraphs=[],
        )
        other_slide = SimpleNamespace(
            slide_number=2,
            builds=[SimpleNamespace(candidate_frames=[SimpleNamespace(frame_number=99)], final_text="Two")],
            paragraphs=[],
        )
        writer.capture_slides([matching_slide, other_slide])
        writer.write()

        self.assertTrue((self.output / "slides" / "slide_0001" / "slide.json").is_file())
        self.assertFalse((self.output / "slides" / "slide_0002").exists())

    def test_capture_does_not_mutate_source_ocr_data(self):
        source = frame()
        original_box = source.ocr_results[0].bounding_box.copy()
        original_text = source.ocr_results[0].text
        writer = self.writer()
        writer.capture_ocr_frames([source])
        writer.capture_reconstructed_frames([source])

        np.testing.assert_array_equal(source.ocr_results[0].bounding_box, original_box)
        self.assertEqual(source.ocr_results[0].text, original_text)

    def test_slide_diagnostics_explain_withheld_promotion(self):
        text = "VI M"
        box = np.array([10, 10, 20, 15], dtype=float)
        result = OCRResult(text, 0.65, box)
        line = TextLine(text, 10, 15, 10, 20, 0.65, TextType.BODY)
        source = CandidateFrame(
            frame_number=25,
            timestamp=5.0,
            image=np.zeros((1080, 1920, 3), dtype=np.uint8),
            difference_score=0.0,
            ocr_results=[result],
            raw_ocr_results=[result],
            text_lines=[line],
            text_paragraphs=[TextParagraph(text, [line], TextType.BODY)],
        )
        writer = self.writer()
        writer.capture_ocr_frames([source])
        writer.capture_reconstructed_frames([source])
        writer.capture_slides(consolidate_slides([source]))
        writer.write()

        slide_data = json.loads(
            (self.output / "slides" / "slide_0001" / "slide.json").read_text(
                encoding="utf-8"
            )
        )
        assessment = slide_data["promotion_assessments"][0]
        self.assertEqual(assessment["text"], text)
        self.assertEqual(assessment["disposition"], "Not Promoted / Fragment")
        self.assertFalse(assessment["included_in_presentation"])
        self.assertIn("Fragment-like Structure", assessment["reasons"])
        self.assertEqual(assessment["context"]["confidence"], 0.65)
        self.assertEqual(slide_data["post_consolidation_text"], "")


if __name__ == "__main__":
    unittest.main()
