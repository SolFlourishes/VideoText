"""Controlled, opt-in OCR preprocessing experiments.

This module is deliberately separate from the production OCR path.  It uses
the same confidence filter, reading order, and line reconstruction that the
pipeline uses, but never selects or enables a preprocessing variant.
"""

from __future__ import annotations

import csv
import json
from dataclasses import asdict, dataclass, replace
from datetime import datetime, timezone
from pathlib import Path
from time import monotonic
from typing import Callable, Iterable

import cv2
import numpy as np

from accuracy_benchmark import AlignmentCounts, calculate_character_error_rate, calculate_word_error_rate
from models import OCRResult
from ocr_preprocessing import OCRPreprocessingResult, apply_preprocessing_variant, list_preprocessing_variants
from config import MIN_CONFIDENCE
from text_reconstruction import reconstruct_lines


SCHEMA_VERSION = "1.0"
CSV_COLUMNS = (
    "image", "variant", "status", "comparison", "CER", "WER",
    "preprocessing_seconds", "OCR_seconds", "reconstruction_seconds", "total_seconds",
    "original_width", "original_height", "output_width", "output_height",
    "recognized_text", "error",
)


@dataclass(frozen=True)
class OCRPreprocessingExperimentOptions:
    """Explicit options for one deterministic preprocessing experiment."""

    variants: tuple[str, ...] = ("original",)
    reference_text: str | None = None
    continue_on_error: bool = False


@dataclass(frozen=True)
class OCRPreprocessingVariantResult:
    variant: str
    preprocessing_metadata: dict[str, object]
    raw_regions: tuple[dict[str, object], ...]
    raw_text: str
    reconstructed_text: str
    preprocessing_seconds: float
    ocr_seconds: float
    reconstruction_seconds: float
    total_seconds: float
    original_dimensions: tuple[int, int]
    output_dimensions: tuple[int, int]
    character_counts: AlignmentCounts | None
    word_counts: AlignmentCounts | None
    cer: float | None
    wer: float | None
    comparison: str
    status: str = "success"
    error: str = ""
    # Kept out of serialized data; it exists solely to write preprocessed.png.
    preprocessed_image: np.ndarray | None = None


@dataclass(frozen=True)
class OCRPreprocessingExperimentResult:
    image: str
    reference_text: str | None
    variants: tuple[OCRPreprocessingVariantResult, ...]


OCRCallable = Callable[[np.ndarray], Iterable[OCRResult]]


def normalize_variants(variants: Iterable[str]) -> tuple[str, ...]:
    """Validate names and prepend the original baseline exactly once."""

    valid = set(list_preprocessing_variants())
    ordered = []
    for name in ("original", *variants):
        normalized = name.strip().lower()
        if normalized not in valid:
            raise ValueError(f"Unknown preprocessing variant: {name}")
        if normalized not in ordered:
            ordered.append(normalized)
    return tuple(ordered)


def _regions_data(regions: Iterable[OCRResult]) -> tuple[dict[str, object], ...]:
    return tuple(
        {
            "text": region.text,
            "confidence": float(region.confidence),
            "bounding_box": [float(value) for value in region.bounding_box],
        }
        for region in regions
    )


def _compare(candidate: OCRPreprocessingVariantResult, baseline: OCRPreprocessingVariantResult) -> str:
    """Compare scored variants by CER, then WER, against the original."""

    if candidate.cer is None or baseline.cer is None:
        return "unavailable"
    candidate_score = (candidate.cer, candidate.wer if candidate.wer is not None else float("inf"))
    baseline_score = (baseline.cer, baseline.wer if baseline.wer is not None else float("inf"))
    if candidate_score < baseline_score:
        return "improved"
    if candidate_score > baseline_score:
        return "worsened"
    return "unchanged"


def _reconstruct_like_production(regions: list[OCRResult]) -> str:
    """Use the production reading-order filter and existing line reconstruction."""

    filtered = [region for region in regions if region.confidence >= MIN_CONFIDENCE]
    filtered.sort(key=lambda region: (region.top, region.left))
    return "\n".join(line.text for line in reconstruct_lines(filtered))


def _paddle_compatible_image(image: np.ndarray) -> np.ndarray:
    """Keep grayscale artifacts while giving production OCR its BGR input."""

    return cv2.cvtColor(image, cv2.COLOR_GRAY2BGR) if image.ndim == 2 else image


def run_preprocessing_experiment(
    image: np.ndarray,
    ocr_callable: OCRCallable,
    options: OCRPreprocessingExperimentOptions | None = None,
    *,
    image_name: str = "image",
) -> OCRPreprocessingExperimentResult:
    """Run each requested variant once, without mutating input or OCR output."""

    options = options or OCRPreprocessingExperimentOptions()
    results: list[OCRPreprocessingVariantResult] = []
    for variant in normalize_variants(options.variants):
        started = monotonic()
        prepared: OCRPreprocessingResult | None = None
        try:
            preprocessing_started = monotonic()
            prepared = apply_preprocessing_variant(image, variant)
            preprocessing_seconds = monotonic() - preprocessing_started

            ocr_started = monotonic()
            # A shallow list copy preserves the caller's output container and regions.
            regions = list(ocr_callable(_paddle_compatible_image(prepared.image)))
            ocr_seconds = monotonic() - ocr_started

            reconstruction_started = monotonic()
            reconstructed_text = _reconstruct_like_production(regions)
            reconstruction_seconds = monotonic() - reconstruction_started
            if options.reference_text is None:
                character_counts = word_counts = None
                cer = wer = None
            else:
                character_counts, cer = calculate_character_error_rate(options.reference_text, reconstructed_text)
                word_counts, wer = calculate_word_error_rate(options.reference_text, reconstructed_text)
            results.append(OCRPreprocessingVariantResult(
                variant=variant,
                preprocessing_metadata=dict(prepared.parameters),
                raw_regions=_regions_data(regions),
                raw_text="\n".join(region.text for region in regions),
                reconstructed_text=reconstructed_text,
                preprocessing_seconds=preprocessing_seconds,
                ocr_seconds=ocr_seconds,
                reconstruction_seconds=reconstruction_seconds,
                total_seconds=monotonic() - started,
                original_dimensions=prepared.original_dimensions,
                output_dimensions=prepared.output_dimensions,
                character_counts=character_counts,
                word_counts=word_counts,
                cer=cer,
                wer=wer,
                comparison="unavailable",
                preprocessed_image=prepared.image,
            ))
        except Exception as error:
            if not options.continue_on_error:
                raise RuntimeError(f"OCR preprocessing variant '{variant}' failed: {error}") from error
            results.append(OCRPreprocessingVariantResult(
                variant=variant, preprocessing_metadata={}, raw_regions=(), raw_text="",
                reconstructed_text="", preprocessing_seconds=0.0, ocr_seconds=0.0,
                reconstruction_seconds=0.0, total_seconds=monotonic() - started,
                original_dimensions=prepared.original_dimensions if prepared else (int(image.shape[1]), int(image.shape[0])),
                output_dimensions=prepared.output_dimensions if prepared else (0, 0),
                character_counts=None, word_counts=None, cer=None, wer=None,
                comparison="unavailable", status="failed", error=f"{type(error).__name__}: {error}",
                preprocessed_image=prepared.image if prepared else None,
            ))

    baseline = next(result for result in results if result.variant == "original")
    return OCRPreprocessingExperimentResult(
        image=image_name,
        reference_text=options.reference_text,
        variants=tuple(
            result if result.status != "success" else replace(result, comparison=_compare(result, baseline))
            for result in results
        ),
    )


def run_diagnostic_frame_experiment(
    frame_directory: str | Path, ocr_callable: OCRCallable, options: OCRPreprocessingExperimentOptions,
) -> OCRPreprocessingExperimentResult:
    """Opt-in helper for a Task 32B ``frames/<frame_id>`` diagnostic directory."""

    image_path = Path(frame_directory) / "original.png"
    image = cv2.imread(str(image_path))
    if image is None:
        raise FileNotFoundError(f"Diagnostic frame image could not be read: {image_path}")
    return run_preprocessing_experiment(image, ocr_callable, options, image_name=image_path.name)


def _variant_data(result: OCRPreprocessingVariantResult) -> dict[str, object]:
    data = asdict(result)
    data.pop("preprocessed_image", None)
    return data


def _csv_row(image: str, result: OCRPreprocessingVariantResult) -> dict[str, object]:
    return {
        "image": image, "variant": result.variant, "status": result.status,
        "comparison": result.comparison, "CER": result.cer if result.cer is not None else "",
        "WER": result.wer if result.wer is not None else "",
        "preprocessing_seconds": result.preprocessing_seconds, "OCR_seconds": result.ocr_seconds,
        "reconstruction_seconds": result.reconstruction_seconds, "total_seconds": result.total_seconds,
        "original_width": result.original_dimensions[0], "original_height": result.original_dimensions[1],
        "output_width": result.output_dimensions[0], "output_height": result.output_dimensions[1],
        "recognized_text": result.reconstructed_text, "error": result.error,
    }


def _write_csv(path: Path, rows: Iterable[dict[str, object]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as output:
        writer = csv.DictWriter(output, fieldnames=CSV_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)


def _format_rate(value: float | None) -> str:
    return "not scored" if value is None else f"{value:.2%}"


def _summary(result: OCRPreprocessingExperimentResult) -> str:
    successful = [item for item in result.variants if item.status == "success"]
    lines = [f"# OCR preprocessing experiment: {result.image}", "", "## Results", ""]
    for item in result.variants:
        lines.append(f"- **{item.variant}**: {item.status}; CER {_format_rate(item.cer)}; WER {_format_rate(item.wer)}; {item.comparison}")
        if item.error:
            lines.append(f"  - Error: {item.error}")
    if successful:
        fastest = min(successful, key=lambda item: (item.total_seconds, item.variant))
        lines.extend(["", f"Fastest: **{fastest.variant}** ({fastest.total_seconds:.3f}s)."])
        scored = [item for item in successful if item.cer is not None]
        if scored:
            best_cer = min(scored, key=lambda item: (item.cer, item.wer if item.wer is not None else float("inf"), item.variant))
            best_wer = min(scored, key=lambda item: (item.wer if item.wer is not None else float("inf"), item.variant))
            lines.extend([f"Best CER: **{best_cer.variant}** ({_format_rate(best_cer.cer)}).", f"Best WER: **{best_wer.variant}** ({_format_rate(best_wer.wer)})."])
    return "\n".join(lines) + "\n"


def _aggregate(experiments: Iterable[OCRPreprocessingExperimentResult]) -> dict[str, object]:
    totals: dict[str, dict[str, int]] = {}
    scored_images = unscored_images = 0
    for experiment in experiments:
        if experiment.reference_text is None:
            unscored_images += 1
            continue
        scored_images += 1
        for result in experiment.variants:
            if result.status != "success" or result.character_counts is None or result.word_counts is None:
                continue
            total = totals.setdefault(result.variant, {"character_edits": 0, "reference_characters": 0, "word_edits": 0, "reference_words": 0})
            total["character_edits"] += result.character_counts.errors
            total["reference_characters"] += len(experiment.reference_text.replace("\r\n", "\n").replace("\r", "\n"))
            total["word_edits"] += result.word_counts.errors
            total["reference_words"] += len(experiment.reference_text.split())
    for total in totals.values():
        total["cer"] = total["character_edits"] / total["reference_characters"] if total["reference_characters"] else None
        total["wer"] = total["word_edits"] / total["reference_words"] if total["reference_words"] else None
    return {"scored_images": scored_images, "unscored_images": unscored_images, "variants": totals}


def write_preprocessing_experiment_report(
    experiments: Iterable[OCRPreprocessingExperimentResult], output_directory: str | Path, *,
    source_inputs: Iterable[str] = (), ocr_configuration: dict[str, object] | None = None,
) -> Path:
    """Write deterministic per-image and root report artifacts for experiments."""

    experiments = tuple(experiments)
    destination = Path(output_directory)
    destination.mkdir(parents=True, exist_ok=True)
    all_rows = []
    for experiment in experiments:
        image_root = destination / Path(experiment.image).stem
        image_root.mkdir(parents=True, exist_ok=True)
        rows = []
        for result in experiment.variants:
            variant_root = image_root / result.variant
            variant_root.mkdir(parents=True, exist_ok=True)
            if result.preprocessed_image is not None and not cv2.imwrite(str(variant_root / "preprocessed.png"), result.preprocessed_image):
                raise OSError(f"Could not write preprocessed experiment image: {variant_root / 'preprocessed.png'}")
            (variant_root / "raw_regions.json").write_text(json.dumps(list(result.raw_regions), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            (variant_root / "raw_text.txt").write_text(result.raw_text, encoding="utf-8")
            (variant_root / "reconstructed_text.txt").write_text(result.reconstructed_text, encoding="utf-8")
            (variant_root / "metrics.json").write_text(json.dumps(_variant_data(result), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            row = _csv_row(experiment.image, result)
            rows.append(row)
            all_rows.append(row)
        (image_root / "image_experiment.json").write_text(json.dumps({"schema_version": SCHEMA_VERSION, "image": experiment.image, "reference_text": experiment.reference_text, "variants": [_variant_data(item) for item in experiment.variants]}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        (image_root / "summary.md").write_text(_summary(experiment), encoding="utf-8")
        _write_csv(image_root / "comparison.csv", rows)
    aggregate = _aggregate(experiments)
    report = {"schema_version": SCHEMA_VERSION, "timestamp": datetime.now(timezone.utc).isoformat(), "source_inputs": list(source_inputs), "selected_variants": list(normalize_variants(item.variant for item in experiments[0].variants)) if experiments else [], "ocr_configuration": ocr_configuration or {}, "preprocessing_configuration": {"variants": list_preprocessing_variants()}, "per_image_results": [{"image": item.image, "reference_text": item.reference_text, "variants": [_variant_data(result) for result in item.variants]} for item in experiments], "aggregate_results": aggregate}
    (destination / "experiment.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (destination / "summary.md").write_text("# OCR preprocessing experiments\n\n" + "\n".join(_summary(item) for item in experiments) + f"\n## Aggregate\n\nScored images: {aggregate['scored_images']}; unscored images: {aggregate['unscored_images']}.\n", encoding="utf-8")
    _write_csv(destination / "comparison.csv", all_rows)
    return destination
