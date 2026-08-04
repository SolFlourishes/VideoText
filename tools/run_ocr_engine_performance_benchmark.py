"""Run isolated PaddleOCR and RapidOCR performance measurements.

Example:
    .venv/Scripts/python.exe tools/run_ocr_engine_performance_benchmark.py \
        --manifest benchmarks/ocr_engine_v1/manifest.json \
        --output-directory output/task37f_performance --repetitions 5
"""

from __future__ import annotations

import argparse
import importlib.metadata
import importlib.util
import json
import os
from pathlib import Path
import platform
import subprocess
import sys
import tempfile
import threading
import time
from typing import Any

import cv2
import psutil

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from ocr_engine_benchmark import load_engine_benchmark_manifest
from ocr_engine_performance_benchmark import (
    PerformanceRun, bytes_to_mb, parse_child_result, performance_report_data,
    write_performance_reports,
)


def _directory_size(path: Path, excluded_directories: tuple[Path, ...] = ()) -> int:
    """Measure files below ``path`` while avoiding overlapping component totals."""

    resolved_exclusions = tuple(directory.resolve() for directory in excluded_directories)
    return sum(
        item.stat().st_size
        for item in path.rglob("*")
        if item.is_file() and not any(exclusion in item.resolve().parents for exclusion in resolved_exclusions)
    ) if path.exists() else 0


def _package_path(package: str) -> Path | None:
    spec = importlib.util.find_spec(package)
    return Path(spec.submodule_search_locations[0]) if spec and spec.submodule_search_locations else None


def _size_components(engine_name: str) -> tuple[dict[str, float], float, float, float]:
    """Measure distinct installed/runtime directories actually present on disk."""

    package_names = ("paddleocr", "paddle", "paddlex") if engine_name == "paddle" else ("rapidocr", "onnxruntime")
    rapid_models = (_package_path("rapidocr") / "models") if _package_path("rapidocr") else None
    components = {
        name: bytes_to_mb(_directory_size(path, (rapid_models,) if name == "rapidocr" and rapid_models else ()))
        for name in package_names if (path := _package_path(name))
    }
    paddle_cache = Path.home() / ".paddlex"
    if engine_name == "rapidocr":
        model_size = bytes_to_mb(_directory_size(rapid_models)) if rapid_models else 0.0
        cache_size = 0.0
    else:
        selected_models = ("PP-LCNet_x1_0_doc_ori", "UVDoc", "PP-LCNet_x1_0_textline_ori", "PP-OCRv5_server_det", "en_PP-OCRv5_mobile_rec")
        model_size = bytes_to_mb(sum(_directory_size(paddle_cache / "official_models" / name) for name in selected_models))
        cache_size = bytes_to_mb(_directory_size(paddle_cache))
    return components, sum(components.values()), model_size, cache_size


def _hardware_profile() -> dict[str, Any]:
    memory = psutil.virtual_memory()
    gpu_name = gpu_memory_mb = None
    try:
        query = subprocess.run(["nvidia-smi", "--query-gpu=name,memory.total", "--format=csv,noheader"], capture_output=True, text=True, check=False, timeout=5)
        if query.returncode == 0 and query.stdout.strip():
            gpu_name, memory_text = query.stdout.splitlines()[0].split(",", 1)
            gpu_memory_mb = memory_text.strip()
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass
    return {
        "os": platform.platform(), "cpu": platform.processor() or None,
        "physical_cores": psutil.cpu_count(logical=False), "logical_cores": psutil.cpu_count(logical=True),
        "ram_mb": bytes_to_mb(memory.total), "gpu_name": gpu_name, "gpu_memory": gpu_memory_mb,
        "python": platform.python_version(), "thread_environment": {name: os.environ.get(name) for name in ("OMP_NUM_THREADS", "MKL_NUM_THREADS", "OPENBLAS_NUM_THREADS") if name in os.environ},
    }


class _RssSampler:
    def __init__(self, process: psutil.Process) -> None:
        self.process = process
        self.peak = process.memory_info().rss
        self.stop_event = threading.Event()
        self.thread = threading.Thread(target=self._sample, daemon=True)

    def _sample(self) -> None:
        while not self.stop_event.wait(0.01):
            self.peak = max(self.peak, self.process.memory_info().rss)

    def __enter__(self):
        self.thread.start()
        return self

    def __exit__(self, *_):
        self.stop_event.set()
        self.thread.join()
        self.peak = max(self.peak, self.process.memory_info().rss)


def _child_engine(engine_name: str):
    if engine_name == "paddle":
        from ocr_engine import PaddleOCREngine
        return PaddleOCREngine(), "paddleocr", "cpu"
    if engine_name == "rapidocr":
        from rapidocr_engine import RapidOCREngine
        return RapidOCREngine(), "rapidocr", "cpu"
    raise ValueError(f"Unknown benchmark engine: {engine_name}")


def _run_child(engine_name: str, manifest_path: Path, run_number: int) -> dict[str, Any]:
    frames = load_engine_benchmark_manifest(manifest_path)
    images = []
    for frame in frames:
        image = cv2.imread(str(frame.image_path))
        if image is None:
            raise RuntimeError(f"Could not read benchmark image: {frame.image_path}")
        images.append(image)
    process = psutil.Process()
    baseline = process.memory_info().rss
    engine, package_name, device_mode = _child_engine(engine_name)
    with _RssSampler(process) as sampler:
        started = time.perf_counter()
        initialize_started = time.perf_counter()
        engine.initialize()
        initialization_seconds = time.perf_counter() - initialize_started
        post_init = process.memory_info().rss
        frame_seconds = []
        for image in images:
            frame_started = time.perf_counter()
            engine.recognize(image)
            frame_seconds.append(time.perf_counter() - frame_started)
        total_seconds = time.perf_counter() - started
    components, package_size, model_size, cache_size = _size_components(engine_name)
    hardware = _hardware_profile()
    hardware["runtime_backend"] = "PaddleOCR/PaddlePaddle" if engine_name == "paddle" else "RapidOCR/ONNX Runtime"
    hardware["process_priority"] = process.nice()
    return {
        "engine_name": engine_name, "engine_version": importlib.metadata.version(package_name),
        "run_number": run_number, "frame_count": len(images), "initialization_seconds": initialization_seconds,
        "first_frame_seconds": frame_seconds[0], "warm_frame_mean_seconds": sum(frame_seconds[1:]) / len(frame_seconds[1:]) if len(frame_seconds) > 1 else None,
        "ocr_seconds": sum(frame_seconds), "total_seconds": total_seconds,
        "baseline_rss_mb": bytes_to_mb(baseline), "post_init_rss_mb": bytes_to_mb(post_init),
        "peak_rss_mb": bytes_to_mb(sampler.peak), "package_size_mb": package_size,
        "model_size_mb": model_size, "cache_size_mb": cache_size, "device_mode": device_mode,
        "hardware_profile": hardware, "package_components_mb": components,
    }


def _child_main(args) -> int:
    try:
        result = {"status": "success", "measurement": _run_child(args.engine, args.manifest, args.run_number)}
    except Exception as error:
        result = {"status": "failure", "error": f"{type(error).__name__}: {error}"}
    Path(args.result_path).write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return 0 if result["status"] == "success" else 1


def _parent_main(args) -> int:
    frames = load_engine_benchmark_manifest(args.manifest)
    if not frames:
        raise RuntimeError("Benchmark manifest contains no frames.")
    runs = []
    for engine in ("paddle", "rapidocr"):
        for run_number in range(1, args.repetitions + 1):
            with tempfile.TemporaryDirectory() as temporary:
                result_path = Path(temporary) / "child-result.json"
                command = [sys.executable, str(Path(__file__).resolve()), "--child", "--engine", engine, "--manifest", str(args.manifest), "--run-number", str(run_number), "--result-path", str(result_path)]
                started = time.perf_counter()
                completed = subprocess.run(command, cwd=Path.cwd(), capture_output=True, text=True, check=False)
                wall_seconds = time.perf_counter() - started
                if completed.returncode:
                    detail = completed.stderr.strip() or completed.stdout.strip()
                    raise RuntimeError(f"{engine} child run {run_number} failed: {detail}")
                measurement = parse_child_result(result_path)
                measurement["process_startup_seconds"] = max(0.0, wall_seconds - measurement["total_seconds"])
                runs.append(PerformanceRun(**measurement))
                print(f"{engine} run {run_number}/{args.repetitions}: {measurement['total_seconds']:.3f}s")
    paths = write_performance_reports(performance_report_data(runs), args.output_directory)
    print("Performance reports written to:")
    for path in paths:
        print(path)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run isolated OCR-engine performance measurements.")
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--output-directory", type=Path, required=False)
    parser.add_argument("--repetitions", type=int, default=5)
    parser.add_argument("--child", action="store_true")
    parser.add_argument("--engine", choices=("paddle", "rapidocr"))
    parser.add_argument("--run-number", type=int)
    parser.add_argument("--result-path", type=Path)
    args = parser.parse_args(argv)
    if args.child:
        if not all((args.engine, args.run_number, args.result_path)):
            parser.error("--child requires --engine, --run-number, and --result-path")
        return _child_main(args)
    if args.output_directory is None or args.repetitions < 1:
        parser.error("parent mode requires --output-directory and positive --repetitions")
    return _parent_main(args)


if __name__ == "__main__":
    raise SystemExit(main())
