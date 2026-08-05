"""Run the verified v2 corpus through PaddleOCR and isolated RapidOCR."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import cv2

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from accuracy_benchmark import calculate_character_error_rate, calculate_word_error_rate
from authoritative_benchmark_reporting import write_authoritative_reports
from ocr_engine_benchmark import EngineBenchmarkFrame, evaluate_engine_frame, normalize_benchmark_text


def load_corpus(root: Path) -> tuple[list[tuple[EngineBenchmarkFrame, dict]], dict]:
    """Load only verified v2 references and their frame metadata."""

    manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    truth = json.loads((root / "ground_truth.json").read_text(encoding="utf-8"))
    records = {record["frame_id"]: record for record in truth["records"]}
    frames: list[tuple[EngineBenchmarkFrame, dict]] = []
    for item in manifest["frames"]:
        record = records[item["frame_id"]]
        if record["verification_status"] != "Verified":
            raise ValueError(f"Reference is not verified: {item['frame_id']}")
        frame = EngineBenchmarkFrame(
            item["frame_id"], root / item["image"], record["reference_text"],
            item["selection_reason"], tuple(item["layout_categories"]), record["notes"],
        )
        frames.append((frame, record))
    return frames, truth


def classify(reference: str, candidate: str) -> list[str]:
    """Classify visible reconstructed-text differences without correcting them."""

    expected = normalize_benchmark_text(reference)
    actual = normalize_benchmark_text(candidate)
    if expected == actual:
        return ["exact"]
    labels: list[str] = []
    if expected.replace(" ", "") == actual.replace(" ", ""):
        labels.append("spacing")
    if expected.casefold() == actual.casefold():
        labels.append("capitalization")
    if re.sub(r"[^\w\s]", "", expected) == re.sub(r"[^\w\s]", "", actual):
        labels.append("punctuation")
    if len(actual.split()) < len(expected.split()):
        labels.append("merged words or missed content")
    if len(actual.split()) > len(expected.split()):
        labels.append("split words or false-positive content")
    return labels or ["recognition/reconstruction difference"]


def aggregate(rows: list[dict], category: str | None = None) -> dict[str, dict]:
    """Calculate exact corpus-weighted accuracy from stored per-frame results."""

    selected = [row for row in rows if category is None or category in row["categories"]]
    output: dict[str, dict] = {}
    for engine in ("paddle", "rapidocr"):
        items = [row for row in selected if row["engine"] == engine]
        totals = {"raw_chars": 0, "raw_words": 0, "reconstructed_chars": 0, "reconstructed_words": 0, "characters": 0, "words": 0}
        for row in items:
            reference = normalize_benchmark_text(row["reference_text"])
            raw = normalize_benchmark_text(row["raw_ocr_text"])
            reconstructed = normalize_benchmark_text(row["reconstructed_text"])
            totals["raw_chars"] += calculate_character_error_rate(reference, raw)[0].errors
            totals["raw_words"] += calculate_word_error_rate(reference, raw)[0].errors
            totals["reconstructed_chars"] += calculate_character_error_rate(reference, reconstructed)[0].errors
            totals["reconstructed_words"] += calculate_word_error_rate(reference, reconstructed)[0].errors
            totals["characters"] += len(reference)
            totals["words"] += len(reference.split())
        output[engine] = {
            "frames": len(items),
            "raw_cer": totals["raw_chars"] / totals["characters"] if totals["characters"] else None,
            "raw_wer": totals["raw_words"] / totals["words"] if totals["words"] else None,
            "reconstructed_cer": totals["reconstructed_chars"] / totals["characters"] if totals["characters"] else None,
            "reconstructed_wer": totals["reconstructed_words"] / totals["words"] if totals["words"] else None,
            "raw_exact_percent": 100 * sum(row["raw_exact_match"] for row in items) / len(items) if items else None,
            "reconstructed_exact_percent": 100 * sum(row["reconstructed_exact_match"] for row in items) / len(items) if items else None,
        }
    return output


def _correlation(values: list[float], outcomes: list[float]) -> float | None:
    """Return a descriptive Pearson correlation only when it is defined."""

    if len(values) < 2 or len(set(values)) < 2 or len(set(outcomes)) < 2:
        return None
    average_values = sum(values) / len(values)
    average_outcomes = sum(outcomes) / len(outcomes)
    numerator = sum((value - average_values) * (outcome - average_outcomes) for value, outcome in zip(values, outcomes))
    denominator = (sum((value - average_values) ** 2 for value in values) * sum((outcome - average_outcomes) ** 2 for outcome in outcomes)) ** 0.5
    return numerator / denominator


def main() -> None:
    """Run evaluation engines and write complete authoritative reports."""

    from ocr_engine import PaddleOCREngine
    from rapidocr_engine import RapidOCREngine
    from authoritative_benchmark_reporting import confidence_summary

    root = Path("benchmarks/ocr_engine_v2")
    output_directory = Path("output/task37k_authoritative_benchmark")
    frames, truth = load_corpus(root)
    engines = (("paddle", "3.3.3", PaddleOCREngine()), ("rapidocr", "3.9.1", RapidOCREngine()))
    rows: list[dict] = []
    for engine_name, engine_version, engine in engines:
        for frame, record in frames:
            image = cv2.imread(str(frame.image_path))
            result = evaluate_engine_frame(engine, engine_name, engine_version, frame, image)
            rows.append({
                "engine": engine_name, "engine_version": engine_version, "frame_id": frame.frame_id,
                "categories": list(frame.layout_categories), "reference_text": frame.reference_text,
                "raw_ocr_text": result.raw_ocr_text, "reconstructed_text": result.reconstructed_text,
                "region_count": result.region_count, "raw_cer": result.raw_metrics.cer, "raw_wer": result.raw_metrics.wer,
                "raw_exact_match": result.raw_metrics.exact_match, "reconstructed_cer": result.reconstructed_metrics.cer,
                "reconstructed_wer": result.reconstructed_metrics.wer, "reconstructed_exact_match": result.reconstructed_metrics.exact_match,
                "confidence": confidence_summary(list(result.confidences)), "confidence_values": list(result.confidences),
                "difference_analysis": classify(frame.reference_text, result.reconstructed_text),
                "missed_content": record["missed_content"], "merged_regions": record["merged_regions"],
                "split_regions": record["split_regions"], "false_positive_content": record["false_positive_content"],
                "ordering_issue": record["ordering_issue"],
            })
    confidence = {engine: confidence_summary([value for row in rows if row["engine"] == engine for value in row["confidence_values"]]) for engine in ("paddle", "rapidocr")}
    correlations = {}
    for engine in ("paddle", "rapidocr"):
        engine_rows = [row for row in rows if row["engine"] == engine and row["confidence"]["mean"] is not None]
        correlations[engine] = {"mean_confidence_vs_reconstructed_cer": _correlation([row["confidence"]["mean"] for row in engine_rows], [row["reconstructed_cer"] for row in engine_rows])}
    categories = sorted({category for row in rows for category in row["categories"]})
    data = {
        "schema_version": 1, "corpus_version": truth["corpus_version"], "authoritative": True,
        "normalization_policy": truth["normalization_policy"], "records": rows, "aggregate": aggregate(rows),
        "category_aggregates": {category: aggregate(rows, category) for category in categories},
        "confidence_distribution": confidence, "confidence_error_correlation": correlations,
        "confidence_note": "Confidence values are engine-native and are not cross-engine calibrated; correlations are descriptive only.",
    }
    write_authoritative_reports(data, output_directory)
    print(output_directory)


if __name__ == "__main__":
    main()
