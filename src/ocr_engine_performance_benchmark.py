"""Evaluation-only helpers for isolated OCR-engine performance measurements."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import csv
import json
import math
from pathlib import Path
import statistics
from typing import Any, Iterable


MEGABYTE = 1024 * 1024


@dataclass(frozen=True)
class PerformanceRun:
    """One fresh-child-process OCR performance measurement."""

    engine_name: str
    engine_version: str
    run_number: int
    frame_count: int
    process_startup_seconds: float
    initialization_seconds: float
    first_frame_seconds: float
    warm_frame_mean_seconds: float | None
    ocr_seconds: float
    total_seconds: float
    baseline_rss_mb: float
    post_init_rss_mb: float
    peak_rss_mb: float
    package_size_mb: float
    model_size_mb: float
    cache_size_mb: float
    device_mode: str
    hardware_profile: dict[str, Any]
    package_components_mb: dict[str, float]


def bytes_to_mb(byte_count: int) -> float:
    """Convert bytes to binary megabytes without rounding the stored value."""

    return byte_count / MEGABYTE


def summarize_measurements(values: Iterable[float | None]) -> dict[str, float | None]:
    """Return deterministic descriptive statistics for available measurements."""

    available = [value for value in values if value is not None]
    if not available:
        return {"minimum": None, "median": None, "mean": None, "maximum": None, "standard_deviation": None}
    return {
        "minimum": min(available),
        "median": statistics.median(available),
        "mean": statistics.mean(available),
        "maximum": max(available),
        "standard_deviation": statistics.stdev(available) if len(available) > 1 else 0.0,
    }


def aggregate_performance_runs(runs: Iterable[PerformanceRun]) -> dict[str, dict[str, Any]]:
    """Aggregate independent run measurements by engine without speed tuning."""

    grouped: dict[str, list[PerformanceRun]] = {}
    for run in runs:
        grouped.setdefault(run.engine_name, []).append(run)
    metrics = (
        "process_startup_seconds", "initialization_seconds", "first_frame_seconds",
        "warm_frame_mean_seconds", "ocr_seconds", "total_seconds", "baseline_rss_mb",
        "post_init_rss_mb", "peak_rss_mb", "package_size_mb", "model_size_mb", "cache_size_mb",
    )
    return {
        engine: {
            "run_count": len(engine_runs),
            "engine_version": engine_runs[0].engine_version,
            "device_mode": engine_runs[0].device_mode,
            "metrics": {metric: summarize_measurements(getattr(run, metric) for run in engine_runs) for metric in metrics},
        }
        for engine, engine_runs in sorted(grouped.items())
    }


def performance_report_data(runs: Iterable[PerformanceRun]) -> dict[str, Any]:
    """Return the stable JSON report schema for isolated child-process results."""

    run_list = list(runs)
    return {
        "schema_version": 1,
        "methodology": {
            "process_isolation": "Each measured run uses one fresh child process.",
            "cold_run": "Models remain installed; no adapter instance exists when the child starts.",
            "warm_inference": "Frames after the first use the initialized adapter in that child.",
            "memory": "RSS is an operating-system process measurement, not exact model allocation.",
        },
        "runs": [asdict(run) for run in run_list],
        "aggregates": aggregate_performance_runs(run_list),
    }


def write_performance_reports(data: dict[str, Any], output_directory: str | Path) -> tuple[Path, Path, Path]:
    """Write machine-readable CSV/JSON and a concise Markdown performance report."""

    directory = Path(output_directory)
    directory.mkdir(parents=True, exist_ok=True)
    csv_path = directory / "ocr_engine_performance.csv"
    json_path = directory / "ocr_engine_performance.json"
    markdown_path = directory / "ocr_engine_performance.md"
    json_path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    fields = [field.name for field in PerformanceRun.__dataclass_fields__.values()]
    with csv_path.open("w", encoding="utf-8", newline="") as report:
        writer = csv.DictWriter(report, fieldnames=fields)
        writer.writeheader()
        for run in data["runs"]:
            writer.writerow({key: json.dumps(value, sort_keys=True) if isinstance(value, dict) else value for key, value in run.items()})
    lines = ["# OCR Engine Performance Benchmark", "", "Each row is a fresh child process; RSS is OS-reported process memory.", "", "| Engine | Runs | Init median | First-frame median | Warm-frame median | OCR total median | Peak RSS median |", "| --- | ---: | ---: | ---: | ---: | ---: | ---: |"]
    for engine, aggregate in data["aggregates"].items():
        metrics = aggregate["metrics"]
        lines.append("| {engine} | {runs} | {init:.3f}s | {first:.3f}s | {warm} | {ocr:.3f}s | {rss:.1f} MB |".format(
            engine=engine, runs=aggregate["run_count"], init=metrics["initialization_seconds"]["median"],
            first=metrics["first_frame_seconds"]["median"],
            warm="n/a" if metrics["warm_frame_mean_seconds"]["median"] is None else f"{metrics['warm_frame_mean_seconds']['median']:.3f}s",
            ocr=metrics["ocr_seconds"]["median"], rss=metrics["peak_rss_mb"]["median"],
        ))
    markdown_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return csv_path, json_path, markdown_path


def parse_child_result(path: str | Path) -> dict[str, Any]:
    """Read one child result and reject malformed or failed protocol data."""

    result_path = Path(path)
    try:
        result = json.loads(result_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise RuntimeError(f"Could not read child benchmark result: {result_path}") from error
    if result.get("status") != "success" or not isinstance(result.get("measurement"), dict):
        raise RuntimeError(result.get("error") or f"Child benchmark failed: {result_path}")
    return result["measurement"]
