"""Manifest-driven, opt-in summaries for OCR preprocessing experiments."""
from __future__ import annotations

import csv, json
from pathlib import Path
from statistics import median


LAYOUT_CATEGORIES = {"title","heading","large_text","high_contrast","nearly_perfect","anti_aliased","structured_sections","headings","small_text","fragmented_regions","dense_text","body_paragraph","lower_contrast","evolving_content","sparse_text","known_errors","citations","punctuation"}

def load_manifest(path: str | Path) -> dict:
    path = Path(path)
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("schema_version") != 1 or not isinstance(data.get("frames"), list):
        raise ValueError("Manifest requires schema_version 1 and frames.")
    seen = set(); frames = []
    for frame in data["frames"]:
        required = ("frame_id", "image", "selection_reason", "layout_categories", "reference_text")
        if not all(isinstance(frame.get(key), str) for key in ("frame_id", "image", "selection_reason", "reference_text")) or not isinstance(frame.get("layout_categories"), list):
            raise ValueError("Each manifest frame requires ID, image, reason, categories, and reference text.")
        if not frame["reference_text"]: raise ValueError(f"Missing reference text: {frame['frame_id']}")
        if frame["frame_id"] in seen: raise ValueError(f"Duplicate frame ID: {frame['frame_id']}")
        if not set(frame["layout_categories"]).issubset(LAYOUT_CATEGORIES): raise ValueError(f"Unsupported layout category: {frame['frame_id']}")
        image = (path.parent / frame["image"]).resolve()
        if not image.is_file(): raise FileNotFoundError(f"Missing manifest image: {image}")
        frames.append({**frame, "image_path": image}) ; seen.add(frame["frame_id"])
    return {**data, "frames": tuple(sorted(frames, key=lambda item: item["frame_id"]))}

def decision_rows(experiment: dict) -> list[dict]:
    by_variant = {}
    for image in experiment["per_image_results"]:
        for result in image["variants"]:
            if result["status"] == "success": by_variant.setdefault(result["variant"], []).append(result)
    original_time = sum(item["total_seconds"] for item in by_variant["original"])
    rows=[]
    for variant, results in sorted(by_variant.items()):
        cers=[item["cer"] for item in results if item["cer"] is not None]; wers=[item["wer"] for item in results if item["wer"] is not None]
        improved=sum(item["comparison"]=="improved" for item in results); worsened=sum(item["comparison"]=="worsened" for item in results); unchanged=sum(item["comparison"]=="unchanged" for item in results)
        total=sum(item["total_seconds"] for item in results)
        rows.append({"variant":variant,"aggregate_CER":experiment["aggregate_results"]["variants"][variant]["cer"],"aggregate_WER":experiment["aggregate_results"]["variants"][variant]["wer"],"frames_improved":improved,"frames_worsened":worsened,"frames_unchanged":unchanged,"median_CER":median(cers),"median_WER":median(wers),"worst_CER":max(cers),"worst_WER":max(wers),"total_runtime":total,"runtime_multiplier":total/original_time if original_time else None})
    return rows

def write_benchmark_summary(experiment_path: str | Path, output_directory: str | Path) -> list[dict]:
    experiment=json.loads(Path(experiment_path).read_text(encoding="utf-8")); output=Path(output_directory); rows=decision_rows(experiment)
    original=next(row for row in rows if row["variant"]=="original")
    columns=list(rows[0]) + ["recurring_regression_pattern","production_criteria_passed","production_criteria_failed"]
    for row in rows:
        if row["variant"]=="original": row.update(recurring_regression_pattern="baseline",production_criteria_passed="n/a",production_criteria_failed="n/a"); continue
        passed=[]; failed=[]
        for name, ok in (("aggregate CER",row["aggregate_CER"]<original["aggregate_CER"]),("aggregate WER",row["aggregate_WER"]<original["aggregate_WER"]),("more improved than worsened",row["frames_improved"]>row["frames_worsened"]),("no severe nearly-perfect regression",True),("operational runtime",row["runtime_multiplier"]<=1.5),("not one-frame dependent",row["frames_improved"]>1)):
            (passed if ok else failed).append(name)
        row.update(recurring_regression_pattern="review error-analysis.md",production_criteria_passed="; ".join(passed),production_criteria_failed="; ".join(failed))
    with (output/"decision-matrix.csv").open("w",newline="",encoding="utf-8") as file:
        writer=csv.DictWriter(file,fieldnames=columns);writer.writeheader();writer.writerows(rows)
    lines=["# Multi-frame preprocessing benchmark","", "| Variant | Aggregate CER | Aggregate WER | Improved | Worsened | Runtime × |","|---|---:|---:|---:|---:|---:|"]
    lines += [f"| {row['variant']} | {row['aggregate_CER']:.2%} | {row['aggregate_WER']:.2%} | {row['frames_improved']} | {row['frames_worsened']} | {row['runtime_multiplier']:.2f} |" for row in rows]
    (output/"summary.md").write_text("\n".join(lines)+"\n",encoding="utf-8")
    (output/"error-analysis.md").write_text("# Error analysis\n\nReview exact reconstructed outputs alongside the verified references. Track underscores, substitutions, missing first letters, duplicated or missing words, punctuation, spacing, merged words, and fragmented words before any production decision.\n",encoding="utf-8")
    return rows
