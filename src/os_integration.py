"""Small operating-system integration points kept separate from GUI code."""

import os
from pathlib import Path
import subprocess
import sys


def default_cli_output_root() -> Path:
    """Return the per-user Documents location used by the CLI by default."""

    return (Path.home() / "Documents" / "VideoText Output").resolve()


def resolve_cli_output_root(output_path: str | Path | None) -> Path:
    """Resolve an explicit CLI path or use the packaging-safe default."""

    if output_path is None or not str(output_path).strip():
        return default_cli_output_root()

    return Path(output_path).expanduser().resolve()


def open_folder(path: str | Path) -> str | None:
    """Open an existing folder and return a nonfatal warning on failure."""

    folder = Path(path)
    if not folder.is_dir():
        return f"Could not open output folder because it does not exist: {folder}"

    try:
        if sys.platform.startswith("win"):
            os.startfile(str(folder))
        elif sys.platform == "darwin":
            subprocess.Popen(["open", str(folder)])
        else:
            subprocess.Popen(["xdg-open", str(folder)])
    except OSError as error:
        return f"Could not open output folder: {error}"

    return None
