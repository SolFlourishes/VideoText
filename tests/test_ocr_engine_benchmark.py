import json
from pathlib import Path
import sys
import tempfile
import unittest

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from models import OCRResult
from ocr_engine import get_registered_ocr_engines
from ocr_engine_benchmark import (
    EngineBenchmarkFrame,
    evaluate_engine_frame,
    load_engine_benchmark_manifest,
    normalize_benchmark_text,
    results_data,
    score_text,
    write_engine_benchmark_reports,
)


class FakeEngine:
    def __init__(self, results):
        self.results = results

    def recognize(self, image):
        return self.results


def region(text, confidence=0.99, box=(0, 0, 10, 10)):
    return OCRResult(text, confidence, np.array(box))


class OCREngineBenchmarkTests(unittest.TestCase):
    def test_normalization_is_shared_and_preserves_case_punctuation_and_bullets(self):
        self.assertEqual(normalize_benchmark_text("caf\u00e9\r\n  • Item!"), "caf\u00e9 • Item!")
        self.assertNotEqual(normalize_benchmark_text("Item"), normalize_benchmark_text("item"))
        self.assertNotEqual(normalize_benchmark_text("• Item"), normalize_benchmark_text("- Item"))

    def test_cer_wer_exact_and_empty_cases_are_deterministic(self):
        exact = score_text("A  line\ntext", "A line text")
        self.assertEqual((exact.cer, exact.wer, exact.exact_match), (0.0, 0.0, True))
        changed = score_text("one two", "one")
        self.assertEqual(changed.word_counts.deletions, 1)
        self.assertEqual(changed.wer, 0.5)
        self.assertIsNone(score_text("", "").cer)
        self.assertIsNone(score_text("", "text").wer)
        self.assertEqual(score_text("text", "").cer, 1.0)
        self.assertEqual(score_text("one two", "one").wer, 0.5)

    def test_raw_and_reconstructed_scores_use_same_policy_without_mutation(self):
        results = [region("Hello", box=(0, 0, 50, 10)), region("world", box=(55, 0, 100, 10))]
        frame = EngineBenchmarkFrame("frame", Path("frame.png"), "Hello world", "test", ("title",))
        evaluated = evaluate_engine_frame(FakeEngine(results), "fake", "1", frame, object())
        self.assertEqual(evaluated.raw_metrics.cer, 0.0)
        self.assertEqual(evaluated.reconstructed_metrics.cer, 0.0)
        self.assertEqual([item.text for item in results], ["Hello", "world"])

    def test_report_schema_and_aggregate_use_all_frame_reference_text(self):
        first = EngineBenchmarkFrame("a", Path("a.png"), "abc", "test", ("title",))
        second = EngineBenchmarkFrame("b", Path("b.png"), "def", "test", ("title",))
        rows = [
            evaluate_engine_frame(FakeEngine([region("abc")]), "fake", "1", first, object()),
            evaluate_engine_frame(FakeEngine([region("de")]), "fake", "1", second, object()),
        ]
        data = results_data({"a": first, "b": second}, rows)
        self.assertEqual(data["aggregates"]["fake"]["raw"]["cer"], 1 / 6)
        self.assertEqual(len(data["results"]), 2)
        with tempfile.TemporaryDirectory() as temporary:
            paths = write_engine_benchmark_reports(data, temporary)
            self.assertTrue(all(path.is_file() for path in paths))
            self.assertEqual(json.loads(paths[1].read_text(encoding="utf-8"))["schema_version"], 1)
            self.assertIn("raw_text_coverage", paths[0].read_text(encoding="utf-8").splitlines()[0])

    def test_manifest_loads_stable_frames_and_rejects_missing_images(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "frame.png").write_bytes(b"image")
            manifest = root / "manifest.json"
            manifest.write_text(json.dumps({"schema_version": 1, "frames": [{"frame_id": "f", "image": "frame.png", "reference_text": "text", "selection_reason": "test", "layout_categories": ["title"]}]}), encoding="utf-8")
            self.assertEqual(load_engine_benchmark_manifest(manifest)[0].frame_id, "f")
            (root / "frame.png").unlink()
            with self.assertRaisesRegex(ValueError, "not found"):
                load_engine_benchmark_manifest(manifest)

    def test_production_registry_remains_paddle_only(self):
        self.assertEqual(get_registered_ocr_engines(), ("paddle",))


if __name__ == "__main__":
    unittest.main()
