"""Reusable OCR and reconstruction accuracy benchmark utilities."""

from __future__ import annotations

import csv
from dataclasses import asdict, dataclass, field
import json
from pathlib import Path
import re
from typing import Iterable


class BenchmarkFormatError(ValueError):
    """Raised when a benchmark reference or candidate file is malformed."""


@dataclass(frozen=True)
class BenchmarkSlide:
    """One slide's text and stable alignment identifiers."""

    slide_id: str
    frame_index: int | None
    text: str
    notes: str | None = None


@dataclass(frozen=True)
class BenchmarkDataset:
    """A reference or candidate dataset in its original input order."""

    video: str | None
    slides: tuple[BenchmarkSlide, ...]
    source_path: Path


@dataclass(frozen=True)
class AlignmentCounts:
    """Levenshtein operation counts for a character or word sequence."""

    substitutions: int = 0
    deletions: int = 0
    insertions: int = 0

    @property
    def errors(self) -> int:
        return self.substitutions + self.deletions + self.insertions


@dataclass(frozen=True)
class SlideAccuracyResult:
    """Per-slide text comparison after deterministic slide alignment."""

    reference_index: int
    candidate_index: int
    reference_slide_id: str
    candidate_slide_id: str
    alignment_method: str
    character_counts: AlignmentCounts
    word_counts: AlignmentCounts
    character_error_rate: float | None
    word_error_rate: float | None
    exact_normalized_match: bool
    reference_character_count: int
    candidate_character_count: int
    reference_word_count: int
    candidate_word_count: int


@dataclass(frozen=True)
class BenchmarkResult:
    """Complete benchmark result, including aligned and unaligned slides."""

    reference: BenchmarkDataset
    candidate: BenchmarkDataset
    slide_results: tuple[SlideAccuracyResult, ...]
    missing_reference_indices: tuple[int, ...]
    unmatched_candidate_indices: tuple[int, ...]
    duplicate_reference_ids: tuple[str, ...]
    duplicate_candidate_ids: tuple[str, ...]
    warnings: tuple[str, ...] = field(default_factory=tuple)


def normalize_text(text: str) -> str:
    """Normalize whitespace for exact comparison without changing case."""

    return re.sub(r"\s+", " ", text.replace("\r\n", "\n").replace("\r", "\n")).strip()


def levenshtein_counts(reference: Iterable[str], candidate: Iterable[str]) -> AlignmentCounts:
    """Return deterministic substitution, deletion, and insertion counts."""

    reference_items = list(reference)
    candidate_items = list(candidate)
    rows, columns = len(reference_items), len(candidate_items)
    distances = [[0] * (columns + 1) for _ in range(rows + 1)]
    for row in range(rows + 1):
        distances[row][0] = row
    for column in range(columns + 1):
        distances[0][column] = column

    for row in range(1, rows + 1):
        for column in range(1, columns + 1):
            substitution_cost = 0 if reference_items[row - 1] == candidate_items[column - 1] else 1
            distances[row][column] = min(
                distances[row - 1][column] + 1,
                distances[row][column - 1] + 1,
                distances[row - 1][column - 1] + substitution_cost,
            )

    substitutions = deletions = insertions = 0
    row, column = rows, columns
    while row or column:
        if row and column and reference_items[row - 1] == candidate_items[column - 1]:
            row -= 1
            column -= 1
        elif row and column and distances[row][column] == distances[row - 1][column - 1] + 1:
            substitutions += 1
            row -= 1
            column -= 1
        elif row and distances[row][column] == distances[row - 1][column] + 1:
            deletions += 1
            row -= 1
        else:
            insertions += 1
            column -= 1
    return AlignmentCounts(substitutions, deletions, insertions)


def _error_rate(counts: AlignmentCounts, reference_count: int) -> float | None:
    """Apply the CER/WER denominator safely when the reference is empty."""

    return counts.errors / reference_count if reference_count else None


def calculate_character_error_rate(reference: str, candidate: str) -> tuple[AlignmentCounts, float | None]:
    """Calculate CER using characters after line-ending normalization only."""

    reference_text = reference.replace("\r\n", "\n").replace("\r", "\n")
    candidate_text = candidate.replace("\r\n", "\n").replace("\r", "\n")
    counts = levenshtein_counts(reference_text, candidate_text)
    return counts, _error_rate(counts, len(reference_text))


def calculate_word_error_rate(reference: str, candidate: str) -> tuple[AlignmentCounts, float | None]:
    """Calculate WER from whitespace-normalized, case-preserving words."""

    reference_words = normalize_text(reference).split()
    candidate_words = normalize_text(candidate).split()
    counts = levenshtein_counts(reference_words, candidate_words)
    return counts, _error_rate(counts, len(reference_words))


def _duplicate_ids(slides: tuple[BenchmarkSlide, ...]) -> tuple[str, ...]:
    counts: dict[str, int] = {}
    for slide in slides:
        counts[slide.slide_id] = counts.get(slide.slide_id, 0) + 1
    return tuple(slide_id for slide_id, count in counts.items() if count > 1)


def align_slides(
    reference: BenchmarkDataset,
    candidate: BenchmarkDataset,
) -> tuple[list[tuple[int, int, str]], tuple[int, ...], tuple[int, ...], tuple[str, ...], tuple[str, ...]]:
    """Align unique IDs first, then unambiguous remaining frame indices."""

    duplicate_reference_ids = _duplicate_ids(reference.slides)
    duplicate_candidate_ids = _duplicate_ids(candidate.slides)
    reference_by_id: dict[str, list[int]] = {}
    candidate_by_id: dict[str, list[int]] = {}
    for index, slide in enumerate(reference.slides):
        reference_by_id.setdefault(slide.slide_id, []).append(index)
    for index, slide in enumerate(candidate.slides):
        candidate_by_id.setdefault(slide.slide_id, []).append(index)

    matches: list[tuple[int, int, str]] = []
    matched_reference: set[int] = set()
    matched_candidate: set[int] = set()
    for slide_id, reference_indices in reference_by_id.items():
        candidate_indices = candidate_by_id.get(slide_id, [])
        if len(reference_indices) == len(candidate_indices) == 1:
            matches.append((reference_indices[0], candidate_indices[0], "slide_id"))
            matched_reference.add(reference_indices[0])
            matched_candidate.add(candidate_indices[0])

    remaining_reference = [index for index in range(len(reference.slides)) if index not in matched_reference]
    remaining_candidate = [index for index in range(len(candidate.slides)) if index not in matched_candidate]
    reference_by_frame: dict[int, list[int]] = {}
    candidate_by_frame: dict[int, list[int]] = {}
    for index in remaining_reference:
        frame_index = reference.slides[index].frame_index
        if frame_index is not None:
            reference_by_frame.setdefault(frame_index, []).append(index)
    for index in remaining_candidate:
        frame_index = candidate.slides[index].frame_index
        if frame_index is not None:
            candidate_by_frame.setdefault(frame_index, []).append(index)
    for frame_index, reference_indices in reference_by_frame.items():
        candidate_indices = candidate_by_frame.get(frame_index, [])
        if len(reference_indices) == len(candidate_indices) == 1:
            matches.append((reference_indices[0], candidate_indices[0], "frame_index"))
            matched_reference.add(reference_indices[0])
            matched_candidate.add(candidate_indices[0])

    matches.sort(key=lambda match: (match[0], match[1]))
    return (
        matches,
        tuple(index for index in range(len(reference.slides)) if index not in matched_reference),
        tuple(index for index in range(len(candidate.slides)) if index not in matched_candidate),
        duplicate_reference_ids,
        duplicate_candidate_ids,
    )


def run_benchmark(reference: BenchmarkDataset, candidate: BenchmarkDataset) -> BenchmarkResult:
    """Align two datasets and calculate all required per-slide metrics."""

    matches, missing_references, unmatched_candidates, duplicate_references, duplicate_candidates = align_slides(reference, candidate)
    results: list[SlideAccuracyResult] = []
    for reference_index, candidate_index, method in matches:
        reference_slide = reference.slides[reference_index]
        candidate_slide = candidate.slides[candidate_index]
        character_counts, cer = calculate_character_error_rate(reference_slide.text, candidate_slide.text)
        word_counts, wer = calculate_word_error_rate(reference_slide.text, candidate_slide.text)
        results.append(SlideAccuracyResult(
            reference_index=reference_index,
            candidate_index=candidate_index,
            reference_slide_id=reference_slide.slide_id,
            candidate_slide_id=candidate_slide.slide_id,
            alignment_method=method,
            character_counts=character_counts,
            word_counts=word_counts,
            character_error_rate=cer,
            word_error_rate=wer,
            exact_normalized_match=normalize_text(reference_slide.text) == normalize_text(candidate_slide.text),
            reference_character_count=len(reference_slide.text.replace("\r\n", "\n").replace("\r", "\n")),
            candidate_character_count=len(candidate_slide.text.replace("\r\n", "\n").replace("\r", "\n")),
            reference_word_count=len(normalize_text(reference_slide.text).split()),
            candidate_word_count=len(normalize_text(candidate_slide.text).split()),
        ))

    warnings = []
    if duplicate_references:
        warnings.append("Duplicate reference slide IDs: " + ", ".join(duplicate_references))
    if duplicate_candidates:
        warnings.append("Duplicate candidate slide IDs: " + ", ".join(duplicate_candidates))
    return BenchmarkResult(reference, candidate, tuple(results), missing_references, unmatched_candidates, duplicate_references, duplicate_candidates, tuple(warnings))


def _read_json(path: Path) -> dict:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as error:
        raise BenchmarkFormatError(f"Benchmark file was not found: {path}") from error
    except UnicodeDecodeError as error:
        raise BenchmarkFormatError(f"Benchmark file is not valid UTF-8: {path}") from error
    except json.JSONDecodeError as error:
        raise BenchmarkFormatError(f"Malformed JSON in {path}: {error.msg}") from error
    if not isinstance(data, dict):
        raise BenchmarkFormatError(f"Benchmark root must be a JSON object: {path}")
    return data


def _dataset_from_json(path: Path, text_field: str) -> BenchmarkDataset:
    data = _read_json(path)
    slides_data = data.get("slides")
    if not isinstance(slides_data, list):
        raise BenchmarkFormatError(f"Benchmark JSON requires a 'slides' array: {path}")
    slides = []
    for index, item in enumerate(slides_data):
        if not isinstance(item, dict):
            raise BenchmarkFormatError(f"Slide {index} must be an object in {path}")
        slide_id = item.get("slide_id")
        if not isinstance(slide_id, str):
            raise BenchmarkFormatError(f"Slide {index} requires a string slide_id in {path}")
        frame_index = item.get("frame_index")
        if frame_index is not None and (isinstance(frame_index, bool) or not isinstance(frame_index, int)):
            raise BenchmarkFormatError(f"Slide {index} frame_index must be an integer or null in {path}")
        text = item.get(text_field)
        if not isinstance(text, str):
            raise BenchmarkFormatError(f"Slide {index} requires a string {text_field} in {path}")
        notes = item.get("notes")
        if notes is not None and not isinstance(notes, str):
            raise BenchmarkFormatError(f"Slide {index} notes must be a string when present in {path}")
        slides.append(BenchmarkSlide(slide_id, frame_index, text, notes))
    video = data.get("video")
    if video is not None and not isinstance(video, str):
        raise BenchmarkFormatError(f"Benchmark video must be a string when present: {path}")
    return BenchmarkDataset(video, tuple(slides), path)


def load_benchmark_dataset(path: str | Path) -> BenchmarkDataset:
    """Load a reference JSON dataset with required ``reference_text`` fields."""

    return _dataset_from_json(Path(path), "reference_text")


def load_candidate_dataset(path: str | Path) -> BenchmarkDataset:
    """Load candidate JSON or VideoText's existing paragraph CSV export."""

    candidate_path = Path(path)
    if candidate_path.suffix.lower() == ".json":
        return _dataset_from_json(candidate_path, "candidate_text")
    if candidate_path.suffix.lower() != ".csv":
        raise BenchmarkFormatError("Candidate input must be a JSON dataset or a VideoText CSV export")
    try:
        with candidate_path.open("r", encoding="utf-8", newline="") as candidate_file:
            reader = csv.DictReader(candidate_file)
            required = {"Slide Number", "Paragraph Text"}
            if reader.fieldnames is None or not required.issubset(reader.fieldnames):
                raise BenchmarkFormatError("Candidate CSV requires Slide Number and Paragraph Text columns")
            grouped: dict[str, list[str]] = {}
            for row_number, row in enumerate(reader, start=2):
                slide_id = (row.get("Slide Number") or "").strip()
                if not slide_id:
                    raise BenchmarkFormatError(f"Candidate CSV has an empty Slide Number at row {row_number}")
                grouped.setdefault(slide_id, []).append(row.get("Paragraph Text") or "")
    except FileNotFoundError as error:
        raise BenchmarkFormatError(f"Candidate file was not found: {candidate_path}") from error
    except UnicodeDecodeError as error:
        raise BenchmarkFormatError(f"Candidate CSV is not valid UTF-8: {candidate_path}") from error
    slides = tuple(BenchmarkSlide(slide_id, None, "\n".join(texts)) for slide_id, texts in grouped.items())
    return BenchmarkDataset(candidate_path.stem, slides, candidate_path)


def _slide_summary(dataset: BenchmarkDataset, indices: tuple[int, ...]) -> list[dict]:
    return [
        {"index": index, "slide_id": dataset.slides[index].slide_id, "frame_index": dataset.slides[index].frame_index}
        for index in indices
    ]


def _counts_data(counts: AlignmentCounts) -> dict:
    return {**asdict(counts), "errors": counts.errors}


def report_data(result: BenchmarkResult) -> dict:
    """Return JSON-serializable benchmark data in deterministic input order."""

    character_counts = AlignmentCounts()
    word_counts = AlignmentCounts()
    reference_characters = reference_words = 0
    for slide_result in result.slide_results:
        character_counts = AlignmentCounts(
            character_counts.substitutions + slide_result.character_counts.substitutions,
            character_counts.deletions + slide_result.character_counts.deletions,
            character_counts.insertions + slide_result.character_counts.insertions,
        )
        word_counts = AlignmentCounts(
            word_counts.substitutions + slide_result.word_counts.substitutions,
            word_counts.deletions + slide_result.word_counts.deletions,
            word_counts.insertions + slide_result.word_counts.insertions,
        )
        reference_characters += slide_result.reference_character_count
        reference_words += slide_result.reference_word_count
    return {
        "metadata": {
            "reference_source": str(result.reference.source_path),
            "candidate_source": str(result.candidate.source_path),
            "video": result.reference.video or result.candidate.video,
        },
        "aggregate_metrics": {
            "character_error_rate": _error_rate(character_counts, reference_characters),
            "word_error_rate": _error_rate(word_counts, reference_words),
            "character_counts": _counts_data(character_counts),
            "word_counts": _counts_data(word_counts),
            "exact_normalized_matches": sum(item.exact_normalized_match for item in result.slide_results),
            "matched_slides": len(result.slide_results),
            "reference_slides": len(result.reference.slides),
            "candidate_slides": len(result.candidate.slides),
            "missing_reference_slides": len(result.missing_reference_indices),
            "unmatched_candidate_slides": len(result.unmatched_candidate_indices),
        },
        "per_slide_metrics": [
            {
                **asdict(item),
                "character_counts": _counts_data(item.character_counts),
                "word_counts": _counts_data(item.word_counts),
            }
            for item in result.slide_results
        ],
        "unmatched_slides": {
            "missing_reference": _slide_summary(result.reference, result.missing_reference_indices),
            "unmatched_candidate": _slide_summary(result.candidate, result.unmatched_candidate_indices),
        },
        "duplicate_identifiers": {
            "reference": list(result.duplicate_reference_ids),
            "candidate": list(result.duplicate_candidate_ids),
        },
        "warnings": list(result.warnings),
        "errors": [],
    }


def write_json_report(result: BenchmarkResult, output_path: str | Path) -> Path:
    """Write the machine-readable benchmark report."""

    destination = Path(output_path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(report_data(result), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return destination


def _format_rate(rate: float | None) -> str:
    return "n/a" if rate is None else f"{rate:.2%}"


def write_markdown_report(result: BenchmarkResult, output_path: str | Path) -> Path:
    """Write a concise, human-readable benchmark report."""

    data = report_data(result)
    aggregate = data["aggregate_metrics"]
    lines = [
        "# VideoText Accuracy Benchmark",
        "",
        f"Video: {data['metadata']['video'] or 'not specified'}",
        "",
        "## Aggregate metrics",
        "",
        f"- Character Error Rate: {_format_rate(aggregate['character_error_rate'])}",
        f"- Word Error Rate: {_format_rate(aggregate['word_error_rate'])}",
        f"- Exact normalized matches: {aggregate['exact_normalized_matches']} of {aggregate['matched_slides']}",
        f"- Coverage: {aggregate['matched_slides']} matched, {aggregate['missing_reference_slides']} missing reference, {aggregate['unmatched_candidate_slides']} unmatched candidate",
        "",
        "## Per-slide summary",
        "",
        "| Reference slide | Candidate slide | Alignment | CER | WER | Exact |",
        "| --- | --- | --- | ---: | ---: | --- |",
    ]
    for item in result.slide_results:
        lines.append(
            f"| {item.reference_slide_id} | {item.candidate_slide_id} | {item.alignment_method} | "
            f"{_format_rate(item.character_error_rate)} | {_format_rate(item.word_error_rate)} | "
            f"{'yes' if item.exact_normalized_match else 'no'} |"
        )
    worst = sorted(result.slide_results, key=lambda item: (item.character_error_rate is None, -(item.character_error_rate or 0), item.reference_index))[:5]
    lines.extend(["", "## Worst-performing slides", ""])
    if worst:
        lines.extend(f"- Slide {item.reference_slide_id}: CER {_format_rate(item.character_error_rate)}, WER {_format_rate(item.word_error_rate)}" for item in worst)
    else:
        lines.append("- No slides were aligned.")
    if result.warnings or result.missing_reference_indices or result.unmatched_candidate_indices:
        lines.extend(["", "## Alignment warnings", ""])
        lines.extend(f"- {warning}" for warning in result.warnings)
        lines.extend(f"- Missing reference slide: {result.reference.slides[index].slide_id}" for index in result.missing_reference_indices)
        lines.extend(f"- Unmatched candidate slide: {result.candidate.slides[index].slide_id}" for index in result.unmatched_candidate_indices)
    destination = Path(output_path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return destination
