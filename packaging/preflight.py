"""Lightweight dependency and metadata checks for the Windows build script."""

import importlib.metadata as metadata
from pathlib import Path
import sys


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SOURCE_DIRECTORY = PROJECT_ROOT / "src"
sys.path.insert(0, str(SOURCE_DIRECTORY))

from app_info import APP_RELEASE


REQUIRED_DISTRIBUTIONS = (
    "PyInstaller",
    "imagesize",
    "paddleocr",
    "paddlepaddle",
    "opencv-python",
    "openpyxl",
)


def main() -> int:
    """Check installed package metadata without importing the OCR runtime."""

    missing = []
    for distribution in REQUIRED_DISTRIBUTIONS:
        try:
            metadata.version(distribution)
        except metadata.PackageNotFoundError:
            missing.append(distribution)

    if missing:
        print("Missing build dependencies: " + ", ".join(missing), file=sys.stderr)
        return 1

    print(f"VideoText release: {APP_RELEASE}")
    print("Build dependency preflight passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
