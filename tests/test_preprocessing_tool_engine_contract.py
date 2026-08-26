"""Contract tests for preprocessing tools' engine-neutral OCR use."""

import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np


sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import ocr_engine
from models import OCRResult


TOOLS_DIRECTORY = Path(__file__).resolve().parent.parent / "tools"


def load_tool(filename: str, module_name: str):
    specification = importlib.util.spec_from_file_location(
        module_name,
        TOOLS_DIRECTORY / filename,
    )
    module = importlib.util.module_from_spec(specification)
    assert specification.loader is not None
    specification.loader.exec_module(module)
    return module


class RecordingEngine:
    def __init__(self, results):
        self.results = results
        self.images = []

    def recognize(self, image):
        self.images.append(image)
        return self.results


class PreprocessingToolEngineContractTests(unittest.TestCase):
    def setUp(self):
        self.image = np.zeros((2, 2, 3), dtype=np.uint8)

    def test_experiment_tool_passes_canonical_results_from_recognize(self):
        module = load_tool(
            "run_preprocessing_experiments.py",
            "preprocessing_experiments_engine_contract",
        )
        region = OCRResult("ordered", 0.9876543, np.array([1, 2, 3, 4]))
        engine = RecordingEngine([region])
        captured = []

        def run_experiment(image, recognize, *_args, **_kwargs):
            captured.append(recognize(image))
            return object()

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "frame.png"
            source.write_bytes(b"input")
            output = root / "output"
            with (
                patch.object(ocr_engine, "get_ocr_engine", return_value=engine),
                patch.object(module.cv2, "imread", return_value=self.image),
                patch.object(module, "run_preprocessing_experiment", side_effect=run_experiment),
                patch.object(module, "write_preprocessing_experiment_report", return_value=output),
            ):
                self.assertEqual(
                    module.main([
                        "--input-image", str(source),
                        "--output-directory", str(output),
                    ]),
                    0,
                )

        self.assertEqual(engine.images, [self.image])
        self.assertIs(captured[0][0], region)
        self.assertEqual(captured[0][0].confidence, 0.9876543)
        self.assertIs(captured[0][0].bounding_box, region.bounding_box)

    def test_benchmark_tool_passes_empty_canonical_results_from_recognize(self):
        module = load_tool(
            "run_preprocessing_benchmark.py",
            "preprocessing_benchmark_engine_contract",
        )
        engine = RecordingEngine([])
        captured = []

        def run_experiment(image, recognize, *_args, **_kwargs):
            captured.append(recognize(image))
            return object()

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "frame.png"
            source.write_bytes(b"input")
            output = root / "output"
            manifest = {
                "frames": [{
                    "image_path": source,
                    "reference_text": "reference",
                    "frame_id": "frame_001",
                }]
            }
            with (
                patch.object(ocr_engine, "get_ocr_engine", return_value=engine),
                patch.object(module, "load_manifest", return_value=manifest),
                patch.object(module.cv2, "imread", return_value=self.image),
                patch.object(module, "run_preprocessing_experiment", side_effect=run_experiment),
                patch.object(module, "write_preprocessing_experiment_report", return_value=output),
                patch.object(module, "write_benchmark_summary"),
            ):
                self.assertEqual(
                    module.main([
                        "--manifest", str(root / "manifest.json"),
                        "--output-directory", str(output),
                    ]),
                    0,
                )

        self.assertEqual(engine.images, [self.image])
        self.assertEqual(captured, [[]])


if __name__ == "__main__":
    unittest.main()
