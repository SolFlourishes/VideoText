"""Focused CSV coverage for document-level raw OCR confidence export."""

import csv
import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np


sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from csv_exporter import CONFIDENCE_STATISTICS_FIELDS
from export_manager import export_all
from models import CandidateFrame, OCRResult, Presentation, Slide, TextParagraph, TextType


def frame(raw_confidences, working_confidences=None) -> CandidateFrame:
    candidate = CandidateFrame(
        frame_number=1,
        timestamp=0.0,
        image=np.zeros((2, 2, 3), dtype=np.uint8),
        difference_score=0.0,
    )
    candidate.raw_ocr_results = [
        OCRResult(f"raw-{index}", confidence, np.array([index, 0, index + 1, 1]))
        for index, confidence in enumerate(raw_confidences)
    ]
    active = raw_confidences if working_confidences is None else working_confidences
    candidate.ocr_results = [
        OCRResult(f"working-{index}", confidence, np.array([index, 1, index + 1, 2]))
        for index, confidence in enumerate(active)
    ]
    return candidate


def presentation() -> Presentation:
    return Presentation(slides=[Slide(
        slide_number=1,
        start_time=0.0,
        end_time=1.0,
        paragraphs=[TextParagraph("Extracted paragraph", text_type=TextType.BODY)],
    )])


class CSVConfidenceExportTests(unittest.TestCase):
    def export_rows(self, frames):
        temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(temporary_directory.cleanup)
        output_path = Path(temporary_directory.name)
        paths = export_all(
            presentation(),
            output_path,
            ["csv"],
            "document",
            candidate_frames=frames,
        )
        with Path(paths["csv"]).open(encoding="utf-8", newline="") as output:
            return list(csv.DictReader(output))

    def test_populated_export_appends_raw_document_confidence_statistics(self):
        rows = self.export_rows([frame([0.59, 0.60, 0.90])])

        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertEqual(
            list(row)[:3],
            ["Slide Number", "Paragraph Type", "Paragraph Text"],
        )
        self.assertEqual(list(row)[3:], list(CONFIDENCE_STATISTICS_FIELDS))
        self.assertEqual(row["Slide Number"], "1")
        self.assertEqual(row["Paragraph Type"], "BODY")
        self.assertEqual(row["Paragraph Text"], "Extracted paragraph")
        self.assertEqual(row["ocr_region_count"], "3")
        self.assertEqual(row["ocr_confidence_minimum"], "0.59")
        self.assertEqual(row["ocr_confidence_maximum"], "0.9")
        self.assertEqual(row["ocr_confidence_mean"], str((0.59 + 0.60 + 0.90) / 3))
        self.assertEqual(row["ocr_confidence_median"], "0.6")
        self.assertEqual(row["ocr_below_threshold_count"], "1")
        self.assertEqual(row["ocr_below_threshold_proportion"], str(1 / 3))
        self.assertEqual(row["ocr_confidence_threshold"], "0.6")

    def test_empty_evidence_exports_zero_counts_and_empty_numeric_values(self):
        row = self.export_rows([frame([])])[0]

        self.assertEqual(row["ocr_region_count"], "0")
        self.assertEqual(row["ocr_below_threshold_count"], "0")
        self.assertEqual(row["ocr_below_threshold_proportion"], "0.0")
        self.assertEqual(row["ocr_confidence_threshold"], "0.6")
        for field in (
            "ocr_confidence_minimum",
            "ocr_confidence_maximum",
            "ocr_confidence_mean",
            "ocr_confidence_median",
        ):
            self.assertEqual(row[field], "")
        self.assertNotIn("nan", ",".join(row.values()).casefold())

    def test_non_finite_raw_values_are_never_written_as_nan(self):
        row = self.export_rows([frame([float("nan")])])[0]

        self.assertEqual(row["ocr_region_count"], "1")
        self.assertEqual(row["ocr_below_threshold_count"], "0")
        self.assertNotIn("nan", ",".join(row.values()).casefold())

    def test_raw_evidence_is_used_and_input_is_not_mutated(self):
        candidate = frame([0.59, 0.90], working_confidences=[0.90])
        raw_before = list(candidate.raw_ocr_results)
        working_before = list(candidate.ocr_results)
        boxes_before = [result.bounding_box.copy() for result in raw_before]

        row = self.export_rows([candidate])[0]

        self.assertEqual(row["ocr_region_count"], "2")
        self.assertEqual(row["ocr_below_threshold_count"], "1")
        self.assertEqual(candidate.raw_ocr_results, raw_before)
        self.assertEqual(candidate.ocr_results, working_before)
        for result, bounding_box in zip(candidate.raw_ocr_results, boxes_before):
            np.testing.assert_array_equal(result.bounding_box, bounding_box)

    def test_legacy_csv_call_remains_unchanged_without_confidence_context(self):
        temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(temporary_directory.cleanup)
        output_path = Path(temporary_directory.name) / "legacy.csv"

        from csv_exporter import export_csv
        export_csv(presentation(), str(output_path))

        with output_path.open(encoding="utf-8", newline="") as output:
            self.assertEqual(list(csv.reader(output)), [
                ["Slide Number", "Paragraph Type", "Paragraph Text"],
                ["1", "BODY", "Extracted paragraph"],
            ])


if __name__ == "__main__":
    unittest.main()
