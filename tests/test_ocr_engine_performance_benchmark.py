from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from ocr_engine import get_default_ocr_engine_name, get_registered_ocr_engines
from ocr_engine_benchmark import load_engine_benchmark_manifest
from ocr_engine_performance_benchmark import (
    PerformanceRun, aggregate_performance_runs, bytes_to_mb, parse_child_result,
    performance_report_data, write_performance_reports,
)


def run(engine="paddle", number=1, total=2.0):
    return PerformanceRun(
        engine_name=engine, engine_version="test", run_number=number, frame_count=4,
        process_startup_seconds=0.5, initialization_seconds=1.0, first_frame_seconds=0.2,
        warm_frame_mean_seconds=0.1, ocr_seconds=0.5, total_seconds=total,
        baseline_rss_mb=10.0, post_init_rss_mb=20.0, peak_rss_mb=25.0,
        package_size_mb=30.0, model_size_mb=40.0, cache_size_mb=50.0, device_mode="cpu",
        hardware_profile={"cpu": "test"}, package_components_mb={"runtime": 30.0},
    )


class OCREnginePerformanceBenchmarkTests(unittest.TestCase):
    def test_memory_conversion_and_aggregate_statistics(self):
        self.assertEqual(bytes_to_mb(1048576), 1.0)
        aggregate = aggregate_performance_runs([run(total=1.0), run(number=2, total=3.0)])["paddle"]
        self.assertEqual(aggregate["run_count"], 2)
        self.assertEqual(aggregate["metrics"]["total_seconds"]["median"], 2.0)
        self.assertAlmostEqual(aggregate["metrics"]["total_seconds"]["standard_deviation"], 2**0.5)

    def test_report_schema_and_generation(self):
        data = performance_report_data([run()])
        self.assertEqual(data["schema_version"], 1)
        self.assertIn("cold_run", data["methodology"])
        with tempfile.TemporaryDirectory() as temporary:
            paths = write_performance_reports(data, temporary)
            self.assertTrue(all(path.is_file() for path in paths))
            self.assertIn("initialization_seconds", paths[0].read_text(encoding="utf-8").splitlines()[0])

    def test_child_result_parsing_and_failure_are_clear(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "result.json"
            path.write_text('{"status": "success", "measurement": {"value": 1}}', encoding="utf-8")
            self.assertEqual(parse_child_result(path), {"value": 1})
            path.write_text('{"status": "failure", "error": "failed child"}', encoding="utf-8")
            with self.assertRaisesRegex(RuntimeError, "failed child"):
                parse_child_result(path)

    def test_paddle_remains_the_only_production_engine(self):
        self.assertEqual(get_registered_ocr_engines(), ("paddle",))
        self.assertEqual(get_default_ocr_engine_name(), "paddle")

    def test_checked_in_corpus_order_is_deterministic(self):
        manifest = Path(__file__).resolve().parent.parent / "benchmarks" / "ocr_engine_v1" / "manifest.json"
        self.assertEqual(
            [frame.frame_id for frame in load_engine_benchmark_manifest(manifest)],
            ["smoke_title_000000", "smoke_bullet_000025", "smoke_progressive_000050", "smoke_compact_000071"],
        )

    def test_rapidocr_remains_outside_production_requirements(self):
        requirements = (Path(__file__).resolve().parent.parent / "requirements.txt").read_text(encoding="utf-8").lower()
        self.assertNotIn("rapidocr", requirements)
        self.assertNotIn("onnxruntime", requirements)


if __name__ == "__main__":
    unittest.main()
