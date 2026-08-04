"""Engine-neutral, reproducible OCR accuracy-benchmark support.

This module is evaluation-only: it does not participate in the production OCR
registry, processing pipeline, checkpoints, or exports.
"""

from __future__ import annotations

import csv
from dataclasses import asdict, dataclass
import json
from pathlib import Path
import re
import unicodedata
from typing import Any, Iterable, Mapping

from accuracy_benchmark import AlignmentCounts, levenshtein_counts
from config import MIN_CONFIDENCE
from models import OCRResult
from text_reconstruction import reconstruct_lines


SCHEMA_VERSION = 1


@dataclass(frozen=True)
class EngineBenchmarkFrame:
    """A human-verified reference transcription and its saved source frame."""

    frame_id: str
    image_path: Path
    reference_text: str
    selection_reason: str
    layout_categories: tuple[str, ...]
    notes: str = ""


@dataclass(frozen=True)
class TextMetrics:
    """Error metrics for one candidate transcription under the shared policy."""

    cer: float | None
    wer: float | None
    exact_match: bool
    character_counts: AlignmentCounts
    word_counts: AlignmentCounts
    text_coverage: float | None


@dataclass(frozen=True)
class EngineFrameBenchmarkResult:
    """Both raw-engine and reconstructed-text measurements for one frame."""

    engine_name: str
    engine_version: str
    frame_id: str
    region_count: int
    raw_ocr_text: str
    reconstructed_text: str
    raw_metrics: TextMetrics
    reconstructed_metrics: TextMetrics
    missed_text_notes: str = ""
    false_positive_text_notes: str = ""


def normalize_benchmark_text(text: str) -> str:
    """Apply the corpus-wide, case- and punctuation-preserving score policy.

    Text is Unicode NFC-normalized. Line endings and every run of whitespace
    become one ASCII space; case, punctuation, and bullet characters remain
    significant. This makes visual wrapping engine-neutral without hiding text
    substitutions such as a missing bullet or changed punctuation.
    """

    normalized = unicodedata.normalize("NFC", text)
    normalized = normalized.replace("\r\n", "\n").replace("\r", "\n")
    return re.sub(r"\s+", " ", normalized).strip()


def _rate(counts: AlignmentCounts, reference_count: int) -> float | None:
    return counts.errors / reference_count if reference_count else None


def score_text(reference: str, candidate: str) -> TextMetrics:
    """Score text with the shared normalization policy and deterministic edits."""

    normalized_reference = normalize_benchmark_text(reference)
    normalized_candidate = normalize_benchmark_text(candidate)
    character_counts = levenshtein_counts(normalized_reference, normalized_candidate)
    reference_words = normalized_reference.split()
    candidate_words = normalized_candidate.split()
    word_counts = levenshtein_counts(reference_words, candidate_words)
    coverage = None
    if normalized_reference:
        coverage = max(0.0, 1.0 - character_counts.deletions / len(normalized_reference))
    return TextMetrics(
        cer=_rate(character_counts, len(normalized_reference)),
        wer=_rate(word_counts, len(reference_words)),
        exact_match=normalized_reference == normalized_candidate,
        character_counts=character_counts,
        word_counts=word_counts,
        text_coverage=coverage,
    )


def reconstruct_benchmark_text(results: list[OCRResult]) -> str:
    """Apply the accepted production line reconstruction to benchmark evidence."""

    working = [result for result in results if result.confidence >= MIN_CONFIDENCE]
    return "\n".join(line.text for line in reconstruct_lines(working))


def evaluate_engine_frame(
    engine: Any,
    engine_name: str,
    engine_version: str,
    frame: EngineBenchmarkFrame,
    image: Any,
) -> EngineFrameBenchmarkResult:
    """Evaluate one engine on one saved frame without changing its results."""

    results = engine.recognize(image)
    raw_text = "\n".join(result.text for result in results)
    reconstructed_text = reconstruct_benchmark_text(results)
    return EngineFrameBenchmarkResult(
        engine_name=engine_name,
        engine_version=engine_version,
        frame_id=frame.frame_id,
        region_count=len(results),
        raw_ocr_text=raw_text,
        reconstructed_text=reconstructed_text,
        raw_metrics=score_text(frame.reference_text, raw_text),
        reconstructed_metrics=score_text(frame.reference_text, reconstructed_text),
    )


def load_engine_benchmark_manifest(path: str | Path) -> tuple[EngineBenchmarkFrame, ...]:
    """Load a versioned frame manifest with exact human-verified references."""

    manifest_path = Path(path)
    data = json.loads(manifest_path.read_text(encoding="utf-8"))
    if data.get("schema_version") != SCHEMA_VERSION or not isinstance(data.get("frames"), list):
        raise ValueError(f"Unsupported OCR-engine benchmark manifest: {manifest_path}")
    frames: list[EngineBenchmarkFrame] = []
    identifiers: set[str] = set()
    for item in data["frames"]:
        frame_id = item.get("frame_id")
        image = item.get("image")
        reference = item.get("reference_text")
        reason = item.get("selection_reason")
        categories = item.get("layout_categories")
        if not all(isinstance(value, str) and value for value in (frame_id, image, reference, reason)):
            raise ValueError("Each benchmark frame requires non-empty ID, image, reference_text, and selection_reason.")
        if frame_id in identifiers or not isinstance(categories, list) or not all(isinstance(value, str) for value in categories):
            raise ValueError(f"Invalid or duplicate benchmark frame: {frame_id!r}")
        image_path = (manifest_path.parent / image).resolve()
        if not image_path.is_file():
            raise ValueError(f"Benchmark image was not found: {image_path}")
        identifiers.add(frame_id)
        frames.append(EngineBenchmarkFrame(frame_id, image_path, reference, reason, tuple(categories), item.get("notes", "")))
    return tuple(frames)


def results_data(
    frames: Mapping[str, EngineBenchmarkFrame],
    results: Iterable[EngineFrameBenchmarkResult],
) -> dict[str, Any]:
    """Build a stable JSON-compatible report with raw and reconstructed scores."""

    rows = list(results)
    engines = sorted({row.engine_name for row in rows})
    aggregates: dict[str, dict[str, Any]] = {}
    for engine in engines:
        engine_rows = [row for row in rows if row.engine_name == engine]
        reference_chars = sum(len(normalize_benchmark_text(frames[row.frame_id].reference_text)) for row in engine_rows)
        reference_words = sum(len(normalize_benchmark_text(frames[row.frame_id].reference_text).split()) for row in engine_rows)
        engine_aggregates: dict[str, Any] = {}
        for name in ("raw_metrics", "reconstructed_metrics"):
            metrics = [getattr(row, name) for row in engine_rows]
            chars = AlignmentCounts(*(sum(getattr(metric.character_counts, part) for metric in metrics) for part in ("substitutions", "deletions", "insertions")))
            words = AlignmentCounts(*(sum(getattr(metric.word_counts, part) for metric in metrics) for part in ("substitutions", "deletions", "insertions")))
            engine_aggregates[name.removesuffix("_metrics")] = {
                "cer": _rate(chars, reference_chars), "wer": _rate(words, reference_words),
                "exact_matches": sum(metric.exact_match for metric in metrics), "frame_count": len(metrics),
                "character_counts": asdict(chars), "word_counts": asdict(words),
            }
        aggregates[engine] = engine_aggregates
    return {
        "schema_version": SCHEMA_VERSION,
        "normalization": "NFC; all whitespace collapsed; case, punctuation, and bullets preserved.",
        "aggregates": aggregates,
        "results": [
            {
                "engine": row.engine_name, "engine_version": row.engine_version, "frame_id": row.frame_id,
                "region_count": row.region_count, "reference_text": frames[row.frame_id].reference_text,
                "raw_ocr_text": row.raw_ocr_text, "reconstructed_text": row.reconstructed_text,
                "raw": _metrics_data(row.raw_metrics), "reconstructed": _metrics_data(row.reconstructed_metrics),
                "missed_text_notes": row.missed_text_notes, "false_positive_text_notes": row.false_positive_text_notes,
            } for row in rows
        ],
    }


def _metrics_data(metrics: TextMetrics) -> dict[str, Any]:
    return {"cer": metrics.cer, "wer": metrics.wer, "exact_match": metrics.exact_match,
            "text_coverage": metrics.text_coverage, "character_counts": asdict(metrics.character_counts),
            "word_counts": asdict(metrics.word_counts)}


def write_engine_benchmark_reports(data: dict[str, Any], output_directory: str | Path) -> tuple[Path, Path, Path]:
    """Write additive CSV, JSON, and concise Markdown benchmark reports."""

    directory = Path(output_directory)
    directory.mkdir(parents=True, exist_ok=True)
    json_path = directory / "ocr_engine_benchmark.json"
    csv_path = directory / "ocr_engine_benchmark.csv"
    markdown_path = directory / "ocr_engine_benchmark.md"
    json_path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    fields = ["engine", "engine_version", "frame_id", "region_count", "reference_text", "raw_ocr_text", "reconstructed_text", "raw_cer", "raw_wer", "raw_exact_match", "raw_text_coverage", "reconstructed_cer", "reconstructed_wer", "reconstructed_exact_match", "reconstructed_text_coverage", "missed_text_notes", "false_positive_text_notes"]
    with csv_path.open("w", encoding="utf-8", newline="") as report:
        writer = csv.DictWriter(report, fieldnames=fields)
        writer.writeheader()
        for row in data["results"]:
            writer.writerow({"engine": row["engine"], "engine_version": row["engine_version"], "frame_id": row["frame_id"], "region_count": row["region_count"], "reference_text": row["reference_text"], "raw_ocr_text": row["raw_ocr_text"], "reconstructed_text": row["reconstructed_text"], "raw_cer": row["raw"]["cer"], "raw_wer": row["raw"]["wer"], "raw_exact_match": row["raw"]["exact_match"], "raw_text_coverage": row["raw"]["text_coverage"], "reconstructed_cer": row["reconstructed"]["cer"], "reconstructed_wer": row["reconstructed"]["wer"], "reconstructed_exact_match": row["reconstructed"]["exact_match"], "reconstructed_text_coverage": row["reconstructed"]["text_coverage"], "missed_text_notes": row["missed_text_notes"], "false_positive_text_notes": row["false_positive_text_notes"]})
    lines = ["# OCR Engine Accuracy Benchmark", "", data["normalization"], "", "| Engine | Text | CER | WER | Exact |", "| --- | --- | ---: | ---: | ---: |"]
    for engine, values in data["aggregates"].items():
        for text_kind in ("raw", "reconstructed"):
            value = values[text_kind]
            lines.append(f"| {engine} | {text_kind} | {value['cer']:.2%} | {value['wer']:.2%} | {value['exact_matches']}/{value['frame_count']} |")
    markdown_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return csv_path, json_path, markdown_path
