"""Evaluation-only comparison helpers for identical full-video OCR replays."""

from __future__ import annotations

import csv
from dataclasses import asdict, dataclass
import json
from pathlib import Path
from typing import Any, Iterable

from accuracy_benchmark import calculate_character_error_rate, calculate_word_error_rate
from models import CandidateFrame, Presentation
from ocr_confidence_stats import calculate_document_ocr_confidence_stats
from ocr_engine_benchmark import normalize_benchmark_text


@dataclass(frozen=True)
class EngineEvaluationSummary:
    """Immutable measurements from one engine's replay of shared candidate frames."""

    engine_name: str
    engine_version: str
    candidate_frame_count: int
    raw_region_count: int
    reconstructed_slide_count: int
    total_characters: int
    total_words: int
    mean_confidence: float | None
    median_confidence: float | None
    minimum_confidence: float | None
    below_threshold_count: int
    below_threshold_proportion: float
    threshold: float
    initialization_seconds: float
    ocr_seconds: float
    downstream_seconds: float
    total_seconds: float
    peak_rss_mb: float | None
    exported_paths: dict[str, str]


def presentation_text(slides) -> list[str]:
    """Return canonical slide text in slide and paragraph order."""

    return ["\n".join(paragraph.text for paragraph in slide.paragraphs) for slide in slides]


def raw_ocr_evidence(frames: Iterable[CandidateFrame]) -> list[dict[str, Any]]:
    """Serialize preserved raw regions without changing their values or order."""

    return [{
        "frame_number": frame.frame_number,
        "timestamp": frame.timestamp,
        "regions": [{"text": region.text, "confidence": region.confidence, "bounding_box": region.bounding_box.tolist()} for region in frame.raw_ocr_results],
    } for frame in frames]


def reconstructed_evidence(frames: Iterable[CandidateFrame], presentation: Presentation) -> dict[str, Any]:
    """Serialize shared reading-order and consolidated results for review."""

    return {
        "frames": [{"frame_number": frame.frame_number, "lines": [line.text for line in frame.text_lines], "paragraphs": [paragraph.text for paragraph in frame.text_paragraphs]} for frame in frames],
        "slides": presentation_text(presentation.slides),
    }


def compare_slide_texts(paddle_slides: list[str], rapid_slides: list[str]) -> list[dict[str, Any]]:
    """Align slides deterministically by output order and preserve absences."""

    rows = []
    for index in range(max(len(paddle_slides), len(rapid_slides))):
        paddle = paddle_slides[index] if index < len(paddle_slides) else ""
        rapid = rapid_slides[index] if index < len(rapid_slides) else ""
        character_counts, _ = calculate_character_error_rate(normalize_benchmark_text(paddle), normalize_benchmark_text(rapid))
        word_counts, _ = calculate_word_error_rate(normalize_benchmark_text(paddle), normalize_benchmark_text(rapid))
        notes = ""
        if index >= len(paddle_slides):
            notes = "missing Paddle slide"
        elif index >= len(rapid_slides):
            notes = "missing RapidOCR slide"
        elif normalize_benchmark_text(paddle) == normalize_benchmark_text(rapid):
            notes = "normalized text equal"
        else:
            notes = "text differs; inspect spacing, punctuation, ordering, or OCR evidence"
        rows.append({
            "slide": index + 1, "paddle_text": paddle, "rapidocr_text": rapid,
            "normalized_equal": normalize_benchmark_text(paddle) == normalize_benchmark_text(rapid),
            "character_difference_count": character_counts.errors,
            "word_difference_count": word_counts.errors, "notes": notes,
        })
    return rows


def write_comparison_reports(
    paddle_summary: EngineEvaluationSummary,
    rapid_summary: EngineEvaluationSummary,
    slide_rows: list[dict[str, Any]],
    output_directory: str | Path,
    source: dict[str, Any],
    reference_note: str,
) -> tuple[Path, Path, Path]:
    """Write the required combined JSON, CSV, and concise Markdown reports."""

    directory = Path(output_directory)
    directory.mkdir(parents=True, exist_ok=True)
    data = {
        "schema_version": 1, "source": source, "reference_note": reference_note,
        "engines": {"paddle": asdict(paddle_summary), "rapidocr": asdict(rapid_summary)},
        "per_slide_differences": slide_rows,
    }
    json_path = directory / "sample2_engine_comparison.json"
    csv_path = directory / "sample2_engine_comparison.csv"
    markdown_path = directory / "sample2_engine_comparison.md"
    json_path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    fields = ("slide", "paddle_text", "rapidocr_text", "normalized_equal", "character_difference_count", "word_difference_count", "notes")
    with csv_path.open("w", encoding="utf-8", newline="") as report:
        writer = csv.DictWriter(report, fieldnames=fields)
        writer.writeheader()
        writer.writerows(slide_rows)
    lines = ["# Sample2 OCR Engine Comparison", "", reference_note, "", "| Engine | Frames | Regions | Slides | OCR time | Downstream time | Peak RSS |", "| --- | ---: | ---: | ---: | ---: | ---: | ---: |"]
    for summary in (paddle_summary, rapid_summary):
        peak = "n/a" if summary.peak_rss_mb is None else f"{summary.peak_rss_mb:.1f} MB"
        lines.append(f"| {summary.engine_name} | {summary.candidate_frame_count} | {summary.raw_region_count} | {summary.reconstructed_slide_count} | {summary.ocr_seconds:.3f}s | {summary.downstream_seconds:.3f}s | {peak} |")
    lines.extend(["", "## Per-slide differences", "", "| Slide | Equal after normalization | Character differences | Word differences | Notes |", "| ---: | --- | ---: | ---: | --- |"])
    lines.extend(f"| {row['slide']} | {'yes' if row['normalized_equal'] else 'no'} | {row['character_difference_count']} | {row['word_difference_count']} | {row['notes']} |" for row in slide_rows)
    markdown_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return csv_path, json_path, markdown_path


def summarize_engine(
    engine_name: str, engine_version: str, frames: list[CandidateFrame], presentation: Presentation,
    initialization_seconds: float, ocr_seconds: float, downstream_seconds: float, total_seconds: float,
    peak_rss_mb: float | None, exported_paths: dict[str, str],
) -> EngineEvaluationSummary:
    """Build one engine summary from canonical raw evidence and slide output."""

    statistics = calculate_document_ocr_confidence_stats(frames)
    slide_text = presentation_text(presentation.slides)
    text = "\n".join(slide_text)
    return EngineEvaluationSummary(
        engine_name=engine_name, engine_version=engine_version, candidate_frame_count=len(frames),
        raw_region_count=statistics.region_count, reconstructed_slide_count=len(presentation.slides),
        total_characters=len(text), total_words=len(normalize_benchmark_text(text).split()),
        mean_confidence=statistics.mean, median_confidence=statistics.median, minimum_confidence=statistics.minimum,
        below_threshold_count=statistics.below_threshold_count, below_threshold_proportion=statistics.below_threshold_proportion,
        threshold=statistics.threshold, initialization_seconds=initialization_seconds, ocr_seconds=ocr_seconds,
        downstream_seconds=downstream_seconds, total_seconds=total_seconds, peak_rss_mb=peak_rss_mb,
        exported_paths=exported_paths,
    )
