"""
tests/test_ocr.py

Simple OCR validation.
"""

from pathlib import Path
import cv2
from paddleocr import PaddleOCR


BASE_DIR = Path(__file__).resolve().parent

IMAGE_FOLDER = (
    BASE_DIR.parent
    / "output"
    / "candidate_frames"
)

IMAGES = sorted(IMAGE_FOLDER.glob("*.png"))

if not IMAGES:
    raise FileNotFoundError(
        f"No PNG images found in {IMAGE_FOLDER}"
    )

IMAGE = IMAGES[8]


def main():

    print("Loading image...")
    print(f"Using image: {IMAGE.name}")

    image = cv2.imread(str(IMAGE))

    if image is None:
        raise FileNotFoundError(IMAGE)

    print("Creating OCR engine...")

    ocr = PaddleOCR(
        use_textline_orientation=True,
        lang="en",
    )

    print("Running OCR...")

    result = ocr.predict(image)

    print("\nSUCCESS!\n")

    from pprint import pprint

    print("\nOCR returned:\n")
    pprint(result)


if __name__ == "__main__":
    main()