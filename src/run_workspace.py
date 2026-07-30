"""
run_workspace.py

Creates isolated output directories for VideoText processing runs.
"""

import re
from pathlib import Path


INVALID_FILENAME_CHARACTERS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
RESERVED_WINDOWS_NAMES = {
    "CON",
    "PRN",
    "AUX",
    "NUL",
    *(f"COM{number}" for number in range(1, 10)),
    *(f"LPT{number}" for number in range(1, 10)),
}


def sanitize_video_stem(video_path: str) -> str:
    """Return a filesystem-safe directory and export-file stem."""

    stem = Path(video_path).stem
    sanitized = INVALID_FILENAME_CHARACTERS.sub("_", stem).strip(" .")

    if not sanitized:
        sanitized = "video"

    if sanitized.upper() in RESERVED_WINDOWS_NAMES:
        sanitized = f"_{sanitized}"

    return sanitized


def create_run_directory(
    output_root: Path,
    video_path: str,
) -> tuple[str, Path]:
    """Create and return the first available numbered run directory."""

    output_root.mkdir(parents=True, exist_ok=True)

    stem = sanitize_video_stem(video_path)
    suffix = 1

    while True:
        name = stem if suffix == 1 else f"{stem}_{suffix}"
        run_directory = output_root / name

        try:
            run_directory.mkdir()
            return stem, run_directory
        except FileExistsError:
            suffix += 1


def create_replay_run_directory(
    output_root: Path,
    source_stem: str,
) -> tuple[str, Path]:
    """Create a unique replay workspace without touching the source run."""

    output_root.mkdir(parents=True, exist_ok=True)
    output_stem = sanitize_video_stem(source_stem)
    base_name = f"{output_stem}_replay"
    suffix = 1

    while True:
        name = base_name if suffix == 1 else f"{base_name}_{suffix}"
        run_directory = output_root / name

        try:
            run_directory.mkdir()
            return output_stem, run_directory
        except FileExistsError:
            suffix += 1
