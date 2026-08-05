"""Render the Version 1.5 authoritative OCR benchmark consistently.

This evaluation-only module keeps report wording and derived summary sections
outside the production OCR pipeline.  It consumes already-recorded benchmark
evidence and never invokes an OCR engine.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any
from statistics import mean, median, pstdev


PERFORMANCE_SUMMARY = {
    "paddle": {
        "initialize_seconds": 13.507,
        "first_frame_seconds": 5.007,
        "warm_frame_seconds": 4.383,
        "ocr_total_seconds": 18.157,
        "benchmark_total_seconds": 31.550,
        "post_init_rss_mb": 458.625,
        "init_increase_mb": 404.473,
        "peak_rss_mb": 1255.699,
    },
    "rapidocr": {
        "initialize_seconds": 1.064,
        "first_frame_seconds": 0.763,
        "warm_frame_seconds": 0.635,
        "ocr_total_seconds": 2.667,
        "benchmark_total_seconds": 3.738,
        "post_init_rss_mb": 144.328,
        "init_increase_mb": 90.250,
        "peak_rss_mb": 362.113,
    },
}

RECOMMENDATION = {
    "decision": "Keep Paddle as default.",
    "rationale": (
        "Paddle has the lower authoritative reconstructed CER and WER on the "
        "verified v2 corpus. RapidOCR remains evaluation-only despite its "
        "faster, smaller measured runtime."
    ),
}

LIMITATIONS = [
    "The verified corpus contains nine representative frames; results are not a claim about every presentation layout.",
    "Engine confidence values are native to each engine and are not calibrated for cross-engine comparison.",
    "RapidOCR model redistribution/commercial-use terms, physical offline validation, and isolated PyInstaller validation remain unresolved.",
]

BUCKETS = ((0.00, 0.59), (0.60, 0.69), (0.70, 0.79), (0.80, 0.89), (0.90, 0.94), (0.95, 1.00))


def confidence_summary(values: list[float]) -> dict[str, Any]:
    """Summarize native confidence evidence with stable inclusive buckets."""

    buckets = {f"{start:.2f}–{end:.2f}": 0 for start, end in BUCKETS}
    if not values:
        return {"region_count": 0, "mean": None, "median": None, "minimum": None, "maximum": None, "standard_deviation": None, "quartiles": [None, None, None], "below_threshold_count": 0, "below_threshold_proportion": 0.0, "buckets": buckets}
    ordered = sorted(values)
    quartile = lambda proportion: ordered[round((len(ordered) - 1) * proportion)]
    for start, end in BUCKETS:
        buckets[f"{start:.2f}–{end:.2f}"] = sum(start <= value <= end for value in values)
    below_threshold = sum(value < 0.60 for value in values)
    return {"region_count": len(values), "mean": mean(values), "median": median(values), "minimum": min(values), "maximum": max(values), "standard_deviation": pstdev(values), "quartiles": [quartile(0.25), quartile(0.50), quartile(0.75)], "below_threshold_count": below_threshold, "below_threshold_proportion": below_threshold / len(values), "buckets": buckets}


def enrich_report_data(data: dict[str, Any]) -> dict[str, Any]:
    """Add stable performance, decision, and limitation sections to report data."""

    data["performance_summary"] = PERFORMANCE_SUMMARY
    data["recommendation"] = RECOMMENDATION
    data["limitations"] = LIMITATIONS
    return data


def _value(value: Any) -> str:
    """Serialize a report value without introducing non-finite values."""

    if value is None:
        return ""
    if isinstance(value, bool):
        return str(value).lower()
    return str(value)


def write_authoritative_reports(data: dict[str, Any], output_directory: str | Path) -> tuple[Path, Path, Path]:
    """Write equivalent JSON, CSV, and Markdown authoritative report sections."""

    data = enrich_report_data(data)
    directory = Path(output_directory)
    directory.mkdir(parents=True, exist_ok=True)
    csv_path = directory / "authoritative_benchmark.csv"
    json_path = directory / "authoritative_benchmark.json"
    markdown_path = directory / "authoritative_benchmark.md"
    json_path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    fields = ["section", "engine", "frame_id", "metric", "value", "notes"]
    with csv_path.open("w", encoding="utf-8", newline="") as report:
        writer = csv.DictWriter(report, fieldnames=fields)
        writer.writeheader()
        for engine, metrics in data["aggregate"].items():
            for metric, value in metrics.items():
                writer.writerow({"section": "accuracy_summary", "engine": engine, "metric": metric, "value": _value(value)})
        for engine, metrics in data["performance_summary"].items():
            for metric, value in metrics.items():
                writer.writerow({"section": "performance_summary", "engine": engine, "metric": metric, "value": _value(value)})
        for engine, metrics in data["confidence_distribution"].items():
            for metric, value in metrics.items():
                if metric == "buckets":
                    for bucket, count in value.items():
                        writer.writerow({"section": "confidence_distribution", "engine": engine, "metric": f"bucket_{bucket}", "value": _value(count)})
                else:
                    writer.writerow({"section": "confidence_distribution", "engine": engine, "metric": metric, "value": _value(value)})
        for engine, metrics in data["confidence_error_correlation"].items():
            for metric, value in metrics.items():
                writer.writerow({"section": "confidence_error_correlation", "engine": engine, "metric": metric, "value": _value(value), "notes": data["confidence_note"]})
        writer.writerow({"section": "recommendation", "metric": "decision", "value": data["recommendation"]["decision"], "notes": data["recommendation"]["rationale"]})
        for limitation in data["limitations"]:
            writer.writerow({"section": "limitation", "metric": "limitation", "value": limitation})
        for row in data["records"]:
            writer.writerow({"section": "per_frame", "engine": row["engine"], "frame_id": row["frame_id"], "metric": "reconstructed_cer", "value": _value(row["reconstructed_cer"]), "notes": "|".join(row["difference_analysis"])})

    lines = ["# VideoText Authoritative OCR Benchmark — v2", "", f"Verified corpus: {len(data['records']) // 2} frames.", "", "## Accuracy summary", "", "| Engine | Raw CER | Raw WER | Reconstructed CER | Reconstructed WER | Reconstructed exact |", "| --- | ---: | ---: | ---: | ---: | ---: |"]
    for engine, metrics in data["aggregate"].items():
        lines.append(f"| {engine} | {metrics['raw_cer']:.2%} | {metrics['raw_wer']:.2%} | {metrics['reconstructed_cer']:.2%} | {metrics['reconstructed_wer']:.2%} | {metrics['reconstructed_exact_percent']:.1f}% |")
    lines.extend(["", "## Performance summary", "", "| Engine | Initialize | First frame | Warm frame | OCR total | Benchmark total |", "| --- | ---: | ---: | ---: | ---: | ---: |"])
    for engine, metrics in data["performance_summary"].items():
        lines.append(f"| {engine} | {metrics['initialize_seconds']:.3f}s | {metrics['first_frame_seconds']:.3f}s | {metrics['warm_frame_seconds']:.3f}s | {metrics['ocr_total_seconds']:.3f}s | {metrics['benchmark_total_seconds']:.3f}s |")
    lines.extend(["", "## Confidence distribution", "", "| Engine | Regions | Mean | Median | Minimum | Maximum | Below 60% |", "| --- | ---: | ---: | ---: | ---: | ---: | ---: |"])
    for engine, metrics in data["confidence_distribution"].items():
        lines.append(f"| {engine} | {metrics['region_count']} | {metrics['mean']:.2%} | {metrics['median']:.2%} | {metrics['minimum']:.2%} | {metrics['maximum']:.2%} | {metrics['below_threshold_count']} ({metrics['below_threshold_proportion']:.2%}) |")
        lines.append("  - Buckets: " + "; ".join(f"{bucket}: {count}" for bucket, count in metrics["buckets"].items()) + ".")
    lines.extend(["", data["confidence_note"], "", "## Confidence and error", ""])
    for engine, metrics in data["confidence_error_correlation"].items():
        value = metrics["mean_confidence_vs_reconstructed_cer"]
        lines.append(f"- {engine}: frame mean-confidence versus reconstructed-CER correlation: {value:.3f}" if value is not None else f"- {engine}: correlation unavailable.")
    lines.extend(["", "## Category results", ""])
    for category, values in data["category_aggregates"].items():
        lines.append(f"- {category}: Paddle reconstructed CER {values['paddle']['reconstructed_cer']:.2%}; RapidOCR reconstructed CER {values['rapidocr']['reconstructed_cer']:.2%}.")
    lines.extend(["", "## Recommendation", "", data["recommendation"]["decision"], "", data["recommendation"]["rationale"], "", "## Limitations", ""])
    lines.extend(f"- {limitation}" for limitation in data["limitations"])
    markdown_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return csv_path, json_path, markdown_path
