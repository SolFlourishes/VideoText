"""Focused tests for deterministic OCR accuracy benchmark calculations."""

import json
from pathlib import Path
import sys
import tempfile
import unittest


sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from accuracy_benchmark import (
    BenchmarkDataset,
    BenchmarkFormatError,
    BenchmarkSlide,
    calculate_character_error_rate,
    calculate_word_error_rate,
    load_benchmark_dataset,
    load_candidate_dataset,
    normalize_text,
    report_data,
    run_benchmark,
    write_json_report,
    write_markdown_report,
)


class AccuracyBenchmarkTests(unittest.TestCase):
    def dataset(self, slides, name="dataset.json"):
        return BenchmarkDataset("sample2.mp4", tuple(slides), Path(name))

    def test_identical_text_has_zero_character_and_word_error_rate(self):
        character_counts, cer = calculate_character_error_rate("Activating Event", "Activating Event")
        word_counts, wer = calculate_word_error_rate("Activating Event", "Activating Event")

        self.assertEqual(character_counts.errors, 0)
        self.assertEqual(word_counts.errors, 0)
        self.assertEqual(cer, 0)
        self.assertEqual(wer, 0)

    def test_character_substitution_insertion_and_deletion_are_counted(self):
        substitution, _ = calculate_character_error_rate("cat", "cut")
        insertion, _ = calculate_character_error_rate("cat", "cart")
        deletion, _ = calculate_character_error_rate("cat", "ct")

        self.assertEqual((substitution.substitutions, substitution.deletions, substitution.insertions), (1, 0, 0))
        self.assertEqual((insertion.substitutions, insertion.deletions, insertion.insertions), (0, 0, 1))
        self.assertEqual((deletion.substitutions, deletion.deletions, deletion.insertions), (0, 1, 0))

    def test_word_and_empty_text_metrics_are_safe(self):
        word_counts, wer = calculate_word_error_rate("one two", "one three")
        empty_candidate, cer = calculate_character_error_rate("text", "")
        empty_reference, empty_reference_cer = calculate_character_error_rate("", "text")

        self.assertEqual(word_counts.substitutions, 1)
        self.assertEqual(wer, 0.5)
        self.assertEqual(empty_candidate.deletions, 4)
        self.assertEqual(cer, 1.0)
        self.assertEqual(empty_reference.insertions, 4)
        self.assertIsNone(empty_reference_cer)

    def test_unicode_and_whitespace_normalization_preserve_case(self):
        counts, cer = calculate_character_error_rate("café", "café")

        self.assertEqual(counts.errors, 0)
        self.assertEqual(cer, 0)
        self.assertEqual(normalize_text("  Line one\r\n\tLine two  "), "Line one Line two")
        self.assertNotEqual(normalize_text("VideoText"), normalize_text("videotext"))

    def test_unique_id_alignment_then_frame_index_fallback_is_deterministic(self):
        reference = self.dataset([
            BenchmarkSlide("intro", 10, "Introduction"),
            BenchmarkSlide("duplicate", 20, "Frame matched"),
        ])
        candidate = self.dataset([
            BenchmarkSlide("intro", 99, "Introduction"),
            BenchmarkSlide("different", 20, "Frame matched"),
        ], "candidate.json")

        result = run_benchmark(reference, candidate)

        self.assertEqual([item.alignment_method for item in result.slide_results], ["slide_id", "frame_index"])
        self.assertEqual([item.reference_slide_id for item in result.slide_results], ["intro", "duplicate"])

    def test_missing_unmatched_and_duplicate_ids_are_reported_without_arbitrary_matching(self):
        reference = self.dataset([
            BenchmarkSlide("same", None, "First"),
            BenchmarkSlide("same", None, "Second"),
            BenchmarkSlide("missing", None, "Missing"),
        ])
        candidate = self.dataset([
            BenchmarkSlide("same", None, "Candidate one"),
            BenchmarkSlide("same", None, "Candidate two"),
            BenchmarkSlide("extra", None, "Extra"),
        ], "candidate.json")

        result = run_benchmark(reference, candidate)
        data = report_data(result)

        self.assertEqual(result.slide_results, ())
        self.assertEqual(data["duplicate_identifiers"], {"reference": ["same"], "candidate": ["same"]})
        self.assertEqual([item["slide_id"] for item in data["unmatched_slides"]["missing_reference"]], ["same", "same", "missing"])
        self.assertEqual([item["slide_id"] for item in data["unmatched_slides"]["unmatched_candidate"]], ["same", "same", "extra"])

    def test_unique_missing_and_unmatched_slides_are_reported(self):
        reference = self.dataset([
            BenchmarkSlide("matched", None, "Matched"),
            BenchmarkSlide("missing", None, "Missing"),
        ])
        candidate = self.dataset([
            BenchmarkSlide("matched", None, "Matched"),
            BenchmarkSlide("extra", None, "Extra"),
        ], "candidate.json")

        data = report_data(run_benchmark(reference, candidate))

        self.assertEqual(data["aggregate_metrics"]["matched_slides"], 1)
        self.assertEqual(data["unmatched_slides"]["missing_reference"][0]["slide_id"], "missing")
        self.assertEqual(data["unmatched_slides"]["unmatched_candidate"][0]["slide_id"], "extra")

    def test_json_csv_and_markdown_reports_are_written_in_input_order(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            reference_path = root / "reference.json"
            candidate_path = root / "candidate.csv"
            reference_path.write_text(json.dumps({"video": "sample.mp4", "slides": [
                {"slide_id": "2", "frame_index": None, "reference_text": "Second"},
                {"slide_id": "1", "frame_index": None, "reference_text": "First"},
            ]}), encoding="utf-8")
            candidate_path.write_text("Slide Number,Paragraph Type,Paragraph Text\n2,BODY,Second\n1,BODY,First\n", encoding="utf-8")

            result = run_benchmark(load_benchmark_dataset(reference_path), load_candidate_dataset(candidate_path))
            json_path = write_json_report(result, root / "report.json")
            markdown_path = write_markdown_report(result, root / "report.md")
            report = json.loads(json_path.read_text(encoding="utf-8"))

            self.assertEqual([item["reference_slide_id"] for item in report["per_slide_metrics"]], ["2", "1"])
            self.assertIn("| 2 | 2 | slide_id | 0.00% | 0.00% | yes |", markdown_path.read_text(encoding="utf-8"))
            self.assertEqual(report["aggregate_metrics"]["exact_normalized_matches"], 2)

    def test_malformed_json_and_invalid_slide_values_raise_clear_errors(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            path = Path(temporary_directory) / "bad.json"
            path.write_text("{not json", encoding="utf-8")
            with self.assertRaisesRegex(BenchmarkFormatError, "Malformed JSON"):
                load_benchmark_dataset(path)
            path.write_text(json.dumps({"slides": [{"slide_id": 1, "reference_text": "Text"}]}), encoding="utf-8")
            with self.assertRaisesRegex(BenchmarkFormatError, "string slide_id"):
                load_benchmark_dataset(path)


if __name__ == "__main__":
    unittest.main()
