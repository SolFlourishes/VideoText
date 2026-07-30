import csv
import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from models import OCRResult
from ocr_preprocessing_experiment import (
    OCRPreprocessingExperimentOptions,
    normalize_variants,
    run_preprocessing_experiment,
    write_preprocessing_experiment_report,
)


def region(text, left=0, top=0, confidence=0.99):
    return OCRResult(text, confidence, np.array([left, top, left + 100, top + 20]))


class OCRPreprocessingExperimentTests(unittest.TestCase):
    def setUp(self):
        self.image = np.full((20, 40, 3), 128, dtype=np.uint8)

    def test_original_is_once_and_selected_order_is_deterministic(self):
        self.assertEqual(normalize_variants(("upscale", "original", "upscale", "threshold")), ("original", "upscale", "threshold"))

    def test_ocr_runs_once_per_variant_and_uses_line_reconstruction(self):
        calls = []
        def ocr(image):
            calls.append(image.shape)
            return [region("right", 100), region("left", 0)]
        result = run_preprocessing_experiment(self.image, ocr, OCRPreprocessingExperimentOptions(("grayscale", "upscale")))
        self.assertEqual([item.variant for item in result.variants], ["original", "grayscale", "upscale"])
        self.assertEqual(len(calls), 3)
        self.assertEqual(result.variants[0].reconstructed_text, "left right")

    def test_metrics_and_comparisons(self):
        outputs = iter([[region("bad")], [region("good")], [region("worse")]])
        result = run_preprocessing_experiment(self.image, lambda _: next(outputs), OCRPreprocessingExperimentOptions(("grayscale", "threshold"), "good"))
        self.assertEqual(result.variants[0].comparison, "unchanged")
        self.assertEqual(result.variants[1].comparison, "improved")
        self.assertEqual(result.variants[2].comparison, "worsened")
        self.assertIsNotNone(result.variants[1].cer)
        self.assertIsNotNone(result.variants[1].wer)

    def test_metrics_are_absent_without_reference(self):
        result = run_preprocessing_experiment(self.image, lambda _: [region("text")])
        self.assertIsNone(result.variants[0].cer)
        self.assertEqual(result.variants[0].comparison, "unavailable")

    def test_continue_on_error_preserves_other_variants(self):
        calls = 0
        def ocr(image):
            nonlocal calls
            calls += 1
            if calls == 2:
                raise ValueError("simulated OCR failure")
            return [region("text")]
        result = run_preprocessing_experiment(self.image, ocr, OCRPreprocessingExperimentOptions(("grayscale",), continue_on_error=True))
        self.assertEqual([item.status for item in result.variants], ["success", "failed"])
        calls = 0
        with self.assertRaisesRegex(RuntimeError, "grayscale"):
            run_preprocessing_experiment(self.image, ocr, OCRPreprocessingExperimentOptions(("grayscale",)))

    def test_reports_include_required_artifacts_and_aggregate_totals(self):
        result = run_preprocessing_experiment(self.image, lambda _: [region("good")], OCRPreprocessingExperimentOptions(("grayscale",), "good"), image_name="frame.png")
        with tempfile.TemporaryDirectory() as directory:
            root = write_preprocessing_experiment_report((result,), directory, source_inputs=["frame.png"])
            for variant in ("original", "grayscale"):
                variant_root = root / "frame" / variant
                self.assertTrue((variant_root / "preprocessed.png").is_file())
                self.assertTrue((variant_root / "raw_regions.json").is_file())
                self.assertTrue((variant_root / "reconstructed_text.txt").is_file())
                self.assertTrue((variant_root / "metrics.json").is_file())
            report = json.loads((root / "experiment.json").read_text(encoding="utf-8"))
            self.assertEqual(report["aggregate_results"]["variants"]["original"]["character_edits"], 0)
            with (root / "comparison.csv").open(encoding="utf-8", newline="") as source:
                rows = list(csv.DictReader(source))
            self.assertEqual(len(rows), 2)
            self.assertIn("recognized_text", rows[0])

    def test_low_confidence_regions_are_filtered_like_reading_order(self):
        result = run_preprocessing_experiment(self.image, lambda _: [region("visible"), region("hidden", confidence=0.59)])
        self.assertEqual(result.variants[0].raw_text, "visible\nhidden")
        self.assertEqual(result.variants[0].reconstructed_text, "visible")

    def test_cli_requires_one_input_source(self):
        tool_path = Path(__file__).resolve().parent.parent / "tools" / "run_preprocessing_experiments.py"
        specification = importlib.util.spec_from_file_location("preprocessing_tool", tool_path)
        module = importlib.util.module_from_spec(specification)
        assert specification.loader is not None
        specification.loader.exec_module(module)
        with self.assertRaises(SystemExit):
            module._parser().parse_args(["--output-directory", "reports"])

    def test_cer_tie_uses_wer_as_secondary_comparison(self):
        # Both candidates are one character from the reference; only the
        # baseline changes word tokenization after whitespace normalization.
        outputs = iter([[region("ab")], [region("a  b")]])
        result = run_preprocessing_experiment(self.image, lambda _: next(outputs), OCRPreprocessingExperimentOptions(("contrast",), "a b"))
        self.assertEqual(result.variants[1].comparison, "improved")

    def test_unicode_and_empty_ocr_output_are_scored(self):
        result = run_preprocessing_experiment(self.image, lambda _: [], OCRPreprocessingExperimentOptions(reference_text="café"))
        self.assertGreater(result.variants[0].cer, 0)
        self.assertEqual(result.variants[0].raw_regions, ())

    def test_input_and_ocr_results_are_not_mutated(self):
        source = self.image.copy()
        results = [region("text")]
        run_preprocessing_experiment(self.image, lambda _: results)
        np.testing.assert_array_equal(self.image, source)
        self.assertEqual(results[0].text, "text")

    def test_failed_preprocessing_still_has_an_artifact(self):
        calls = 0
        def ocr(_):
            nonlocal calls
            calls += 1
            if calls == 2:
                raise RuntimeError("failure")
            return []
        result = run_preprocessing_experiment(self.image, ocr, OCRPreprocessingExperimentOptions(("grayscale",), continue_on_error=True), image_name="frame.png")
        with tempfile.TemporaryDirectory() as directory:
            root = write_preprocessing_experiment_report((result,), directory)
            self.assertTrue((root / "frame" / "grayscale" / "preprocessed.png").is_file())

    def test_aggregate_uses_total_edits_not_average_percentages(self):
        first = run_preprocessing_experiment(self.image, lambda _: [region("a")], OCRPreprocessingExperimentOptions(reference_text="a"), image_name="one.png")
        second = run_preprocessing_experiment(self.image, lambda _: [region("")], OCRPreprocessingExperimentOptions(reference_text="abcdefghij"), image_name="two.png")
        with tempfile.TemporaryDirectory() as directory:
            root = write_preprocessing_experiment_report((first, second), directory)
            aggregate = json.loads((root / "experiment.json").read_text(encoding="utf-8"))["aggregate_results"]["variants"]["original"]
        self.assertEqual(aggregate["character_edits"], 10)
        self.assertEqual(aggregate["reference_characters"], 11)
        self.assertAlmostEqual(aggregate["cer"], 10 / 11)

    def test_cli_directory_helpers_are_deterministic_and_allow_missing_references(self):
        tool_path = Path(__file__).resolve().parent.parent / "tools" / "run_preprocessing_experiments.py"
        specification = importlib.util.spec_from_file_location("preprocessing_tool_helpers", tool_path)
        module = importlib.util.module_from_spec(specification)
        assert specification.loader is not None
        specification.loader.exec_module(module)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "z.png").write_bytes(b"")
            (root / "a.jpg").write_bytes(b"")
            (root / "skip.txt").write_text("ignored", encoding="utf-8")
            mapping = root / "references.json"
            mapping.write_text(json.dumps({"a.jpg": "reference"}), encoding="utf-8")
            arguments = module._parser().parse_args(["--input-directory", str(root), "--output-directory", str(root / "out"), "--reference-text", str(mapping)])
            images = module._images(arguments)
            self.assertEqual([path.name for path in images], ["a.jpg", "z.png"])
            self.assertEqual(module._references(arguments, images), {"a.jpg": "reference", "z.png": None})

    def test_cli_directory_without_images_is_rejected(self):
        tool_path = Path(__file__).resolve().parent.parent / "tools" / "run_preprocessing_experiments.py"
        specification = importlib.util.spec_from_file_location("preprocessing_tool_empty", tool_path)
        module = importlib.util.module_from_spec(specification)
        assert specification.loader is not None
        specification.loader.exec_module(module)
        with tempfile.TemporaryDirectory() as directory:
            arguments = module._parser().parse_args(["--input-directory", directory, "--output-directory", directory])
            with self.assertRaisesRegex(ValueError, "No supported images"):
                module._images(arguments)


if __name__ == "__main__":
    unittest.main()
