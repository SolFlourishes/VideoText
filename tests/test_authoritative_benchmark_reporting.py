"""Focused tests for authoritative benchmark report completion."""

from __future__ import annotations

import csv
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from authoritative_benchmark_reporting import confidence_summary, write_authoritative_reports


class AuthoritativeBenchmarkReportingTests(unittest.TestCase):
    def test_confidence_summary_uses_stable_buckets_and_empty_values(self) -> None:
        empty = confidence_summary([])
        self.assertEqual(0, empty["region_count"])
        self.assertIsNone(empty["mean"])
        summary = confidence_summary([0.59, 0.60, 0.95, 1.00])
        self.assertEqual(1, summary["buckets"]["0.00–0.59"])
        self.assertEqual(1, summary["buckets"]["0.60–0.69"])
        self.assertEqual(2, summary["buckets"]["0.95–1.00"])
        self.assertEqual(1, summary["below_threshold_count"])

    def _data(self) -> dict:
        return {
            "records": [{"engine": "paddle", "frame_id": "one", "reconstructed_cer": 0.0, "difference_analysis": ["exact"]}, {"engine": "rapidocr", "frame_id": "one", "reconstructed_cer": 0.1, "difference_analysis": ["spacing"]}],
            "aggregate": {"paddle": {"frames": 1, "raw_cer": 0.0, "raw_wer": 0.0, "reconstructed_cer": 0.0, "reconstructed_wer": 0.0, "raw_exact_percent": 100.0, "reconstructed_exact_percent": 100.0}, "rapidocr": {"frames": 1, "raw_cer": 0.1, "raw_wer": 0.2, "reconstructed_cer": 0.1, "reconstructed_wer": 0.2, "raw_exact_percent": 0.0, "reconstructed_exact_percent": 0.0}},
            "category_aggregates": {"title": {"paddle": {"reconstructed_cer": 0.0}, "rapidocr": {"reconstructed_cer": 0.1}}},
            "confidence_distribution": {"paddle": {"region_count": 1, "mean": 0.9, "median": 0.9, "minimum": 0.9, "maximum": 0.9, "standard_deviation": 0.0, "quartiles": [0.9, 0.9, 0.9], "below_threshold_count": 0, "below_threshold_proportion": 0.0, "buckets": {"0.95–1.00": 0}}, "rapidocr": {"region_count": 0, "mean": 0.0, "median": 0.0, "minimum": 0.0, "maximum": 0.0, "standard_deviation": 0.0, "quartiles": [0.0, 0.0, 0.0], "below_threshold_count": 0, "below_threshold_proportion": 0.0, "buckets": {"0.95–1.00": 0}}},
            "confidence_error_correlation": {"paddle": {"mean_confidence_vs_reconstructed_cer": None}, "rapidocr": {"mean_confidence_vs_reconstructed_cer": None}},
            "confidence_note": "Engine confidence scales are not calibrated.",
        }

    def test_all_report_formats_include_required_summary_sections(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            csv_path, json_path, markdown_path = write_authoritative_reports(self._data(), temporary)
            report = json.loads(json_path.read_text(encoding="utf-8"))
            self.assertIn("performance_summary", report)
            self.assertIn("recommendation", report)
            self.assertIn("limitations", report)
            markdown = markdown_path.read_text(encoding="utf-8")
            for heading in ("Accuracy summary", "Performance summary", "Confidence distribution", "Recommendation", "Limitations"):
                self.assertIn(heading, markdown)
            with csv_path.open(encoding="utf-8", newline="") as report:
                sections = {row["section"] for row in csv.DictReader(report)}
            self.assertTrue({"accuracy_summary", "performance_summary", "confidence_distribution", "recommendation", "limitation"}.issubset(sections))
