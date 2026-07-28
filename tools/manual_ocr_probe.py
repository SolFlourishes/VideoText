"""Manually inspect PaddleOCR output for one candidate-frame image.

This developer diagnostic is not an automated test. It requires the full OCR
runtime (OpenCV, PaddleOCR, and PaddlePaddle) and either ``--image`` or a
candidate-frame directory supplied with ``--candidate-frames-dir``.

Examples:
    python tools/manual_ocr_probe.py --image output/sample/candidate_frames/frame_000001_0.00s.png
    python tools/manual_ocr_probe.py --candidate-frames-dir output/sample/candidate_frames --index 8
"""

import argparse
from pathlib import Path
from pprint import pprint


def parse_arguments() -> argparse.Namespace:
    """Collect an image path or candidate-frame directory from the user."""

    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--image", type=Path, help="PNG image to send to OCR.")
    source.add_argument(
        "--candidate-frames-dir",
        type=Path,
        help="Directory containing candidate-frame PNG images.",
    )
    parser.add_argument(
        "--index",
        type=int,
        default=8,
        help="Zero-based PNG index when using --candidate-frames-dir (default: 8).",
    )
    return parser.parse_args()


def resolve_image(arguments: argparse.Namespace) -> Path | None:
    """Return the requested image or print a clear input error."""

    if arguments.image is not None:
        image = arguments.image
        if image.is_file():
            return image
        print(f"OCR probe input image does not exist: {image}")
        return None

    directory = arguments.candidate_frames_dir
    if not directory.is_dir():
        print(f"OCR probe candidate-frame directory does not exist: {directory}")
        return None

    images = sorted(directory.glob("*.png"))
    if not images:
        print(f"OCR probe found no PNG images in: {directory}")
        return None
    if arguments.index < 0 or arguments.index >= len(images):
        print(
            f"OCR probe index {arguments.index} is outside the available "
            f"range 0-{len(images) - 1} in: {directory}"
        )
        return None
    return images[arguments.index]


def main() -> int:
    """Run OCR for one manually supplied candidate-frame image."""

    arguments = parse_arguments()
    image_path = resolve_image(arguments)
    if image_path is None:
        return 2

    try:
        import cv2
        from paddleocr import PaddleOCR
    except ImportError as error:
        print(
            "OCR probe requires OpenCV, PaddleOCR, and PaddlePaddle. "
            f"Install the OCR runtime before running this tool. ({error})"
        )
        return 1

    print(f"Loading image: {image_path}")
    image = cv2.imread(str(image_path))
    if image is None:
        print(f"OCR probe could not read image: {image_path}")
        return 1

    print("Creating PaddleOCR engine...")
    ocr = PaddleOCR(use_textline_orientation=True, lang="en")
    print("Running OCR...")
    result = ocr.predict(image)

    print("\nOCR returned:\n")
    pprint(result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
