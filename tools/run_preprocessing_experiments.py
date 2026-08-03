"""Run opt-in OCR preprocessing experiments.

Example: ``python tools/run_preprocessing_experiments.py --input-image frame.png
--output-directory experiment --reference-text-inline "Verified text"``.
This tool uses the installed production PaddleOCR model but never alters
VideoText's production preprocessing configuration.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import cv2

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from ocr_preprocessing import list_preprocessing_variants
from ocr_preprocessing_experiment import (
    OCRPreprocessingExperimentOptions,
    run_preprocessing_experiment,
    write_preprocessing_experiment_report,
)


SUPPORTED_SUFFIXES = {".png", ".jpg", ".jpeg", ".bmp"}


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Compare opt-in OCR preprocessing variants.")
    inputs = parser.add_mutually_exclusive_group(required=True)
    inputs.add_argument("--input-image", type=Path)
    inputs.add_argument("--input-directory", type=Path)
    parser.add_argument("--output-directory", type=Path, required=True)
    references = parser.add_mutually_exclusive_group()
    references.add_argument("--reference-text", type=Path, help="UTF-8 text file, or JSON mapping for directory input.")
    references.add_argument("--reference-text-inline")
    parser.add_argument("--variants", nargs="+", choices=list_preprocessing_variants())
    parser.add_argument("--ocr-language", help="Recorded in the report; production currently uses its configured language.")
    parser.add_argument("--device", help="Recorded in the report; production currently chooses its configured device.")
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument("--continue-on-error", action="store_true")
    return parser


def _images(arguments: argparse.Namespace) -> list[Path]:
    if arguments.input_image:
        return [arguments.input_image]
    # A Task 32B frame directory itself contains ``original.png``.
    diagnostic_image = arguments.input_directory / "original.png"
    if diagnostic_image.is_file():
        return [diagnostic_image]
    images = sorted((path for path in arguments.input_directory.iterdir() if path.is_file() and path.suffix.lower() in SUPPORTED_SUFFIXES), key=lambda path: path.name.lower())
    if not images:
        raise ValueError(f"No supported images found in: {arguments.input_directory}")
    return images


def _references(arguments: argparse.Namespace, images: list[Path]) -> dict[str, str | None]:
    if arguments.reference_text_inline is not None:
        return {path.name: arguments.reference_text_inline for path in images}
    if arguments.reference_text is None:
        return {path.name: None for path in images}
    text = arguments.reference_text.read_text(encoding="utf-8")
    if len(images) == 1:
        return {images[0].name: text}
    mapping = json.loads(text)
    if not isinstance(mapping, dict) or not all(isinstance(key, str) and isinstance(value, str) for key, value in mapping.items()):
        raise ValueError("Directory references must be a JSON object mapping image names to text.")
    return {path.name: mapping.get(path.name) for path in images}


def main(argv: list[str] | None = None) -> int:
    parser = _parser()
    arguments = parser.parse_args(argv)
    if arguments.output_directory.exists() and any(arguments.output_directory.iterdir()) and not arguments.overwrite:
        parser.error("output directory is not empty; use --overwrite to replace matching report artifacts")
    try:
        images = _images(arguments)
        references = _references(arguments, images)
    except (OSError, ValueError, json.JSONDecodeError) as error:
        parser.error(str(error))
    # Keep CLI argument validation and unit tests independent of PaddleOCR.
    from ocr_engine import get_ocr_engine
    engine = get_ocr_engine()

    experiments = []
    for image_path in images:
        image = cv2.imread(str(image_path))
        if image is None:
            if arguments.continue_on_error:
                print(f"Skipping unreadable image: {image_path}", file=sys.stderr)
                continue
            parser.error(f"input image could not be read: {image_path}")
        options = OCRPreprocessingExperimentOptions(tuple(arguments.variants or ("original",)), references[image_path.name], arguments.continue_on_error)
        # Task 32B stores every diagnostic image as ``original.png``. Keep its
        # frame directory identifier in reports so measurements remain traceable.
        image_name = image_path.parent.name if image_path.name == "original.png" and image_path.parent.name.startswith("frame_") else image_path.name
        experiments.append(
            run_preprocessing_experiment(
                image,
                engine.recognize,
                options,
                image_name=image_name,
            )
        )
    destination = write_preprocessing_experiment_report(experiments, arguments.output_directory, source_inputs=[str(path) for path in images], ocr_configuration={"language": arguments.ocr_language or "production default", "device": arguments.device or "production default"})
    print(f"Experiment reports written to: {destination}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
