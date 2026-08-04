"""Run the isolated PaddleOCR-versus-RapidOCR benchmark on saved PNG frames.

Example:
    .venv/Scripts/python.exe tools/run_ocr_engine_benchmark.py \
        --manifest benchmarks/ocr_engine_v1/manifest.json \
        --output-directory output/task37e_ocr_engine_benchmark

RapidOCR is imported only here through its unregistered evaluation adapter; it
is not available to VideoText production processing.
"""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

import cv2

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from ocr_engine import PaddleOCREngine
from ocr_engine_benchmark import (
    evaluate_engine_frame,
    load_engine_benchmark_manifest,
    results_data,
    write_engine_benchmark_reports,
)
from rapidocr_engine import RapidOCREngine


def _version(package_name: str) -> str:
    try:
        from importlib.metadata import version

        return version(package_name)
    except Exception:  # Benchmark metadata should not hide a valid OCR result.
        return "unknown"


def main(argv: list[str] | None = None) -> int:
    """Run both isolated adapters on every manifest frame and write reports."""

    parser = argparse.ArgumentParser(description="Compare PaddleOCR and RapidOCR on saved benchmark frames.")
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--output-directory", type=Path, required=True)
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args(argv)
    if args.output_directory.exists() and any(args.output_directory.iterdir()) and not args.overwrite:
        parser.error("output directory is not empty; use --overwrite")

    frames = load_engine_benchmark_manifest(args.manifest)
    engines = (("paddle", _version("paddleocr"), PaddleOCREngine()), ("rapidocr", _version("rapidocr"), RapidOCREngine()))
    results = []
    for frame in frames:
        image = cv2.imread(str(frame.image_path))
        if image is None:
            raise RuntimeError(f"Could not read benchmark image: {frame.image_path}")
        for engine_name, engine_version, engine in engines:
            print(f"{engine_name}: {frame.frame_id}")
            results.append(evaluate_engine_frame(engine, engine_name, engine_version, frame, image))

    frame_map = {frame.frame_id: frame for frame in frames}
    paths = write_engine_benchmark_reports(results_data(frame_map, results), args.output_directory)
    print("Benchmark reports written to:")
    for path in paths:
        print(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
