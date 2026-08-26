from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from full_video_engine_comparison import (
    EngineEvaluationSummary, compare_slide_texts, presentation_text, write_comparison_reports,
)
from ocr_engine import get_default_ocr_engine_name, get_registered_ocr_engines


def summary(engine):
    return EngineEvaluationSummary(engine, "test", 2, 3, 1, 10, 2, .9, .9, .8, 0, 0.0, .6, 1.0, 2.0, 3.0, 4.0, 5.0, {})


class FullVideoEngineComparisonTests(unittest.TestCase):
    def test_deterministic_alignment_and_missing_slide_handling(self):
        rows = compare_slide_texts(["One", "Two"], ["One", "three", "Four"])
        self.assertEqual([row["slide"] for row in rows], [1, 2, 3])
        self.assertTrue(rows[0]["normalized_equal"])
        self.assertEqual(rows[2]["notes"], "missing Paddle slide")

    def test_shared_normalization_distinguishes_raw_and_reconstructed_comparison(self):
        row = compare_slide_texts(["A  line\ntext"], ["A line text"])[0]
        self.assertTrue(row["normalized_equal"])
        self.assertEqual(row["character_difference_count"], 0)

    def test_report_schema_and_isolated_output_directory(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "comparison"
            paths = write_comparison_reports(summary("paddle"), summary("rapidocr"), [], root, {"source": "test"}, "baseline only")
            self.assertTrue(all(path.parent == root and path.is_file() for path in paths))
            self.assertIn("baseline only", paths[2].read_text(encoding="utf-8"))

    def test_production_registry_remains_paddle_only(self):
        self.assertEqual(get_registered_ocr_engines(), ("paddle",))
        self.assertEqual(get_default_ocr_engine_name(), "paddle")


if __name__ == "__main__":
    unittest.main()
