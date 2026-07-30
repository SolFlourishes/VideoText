"""Persistent per-user VideoText preferences, independent of GUI widgets."""

from dataclasses import asdict, dataclass, field
import json
import os
from pathlib import Path
import tempfile


SUPPORTED_EXPORT_FORMATS = ("markdown", "csv", "excel")
RECENT_SOURCE_LIMIT = 10


@dataclass
class Preferences:
    """Small, user-editable settings applied as GUI startup defaults."""

    default_output_folder: str = ""
    default_export_formats: list[str] = field(
        default_factory=lambda: list(SUPPORTED_EXPORT_FORMATS)
    )
    remember_last_folders: bool = True
    open_output_folder_after_completion: bool = False
    last_single_video_folder: str = ""
    last_batch_video_folder: str = ""
    last_batch_folder: str = ""
    last_checkpoint_folder: str = ""
    last_output_folder: str = ""
    recent_sources: list[str] = field(default_factory=list)


def preferences_path() -> Path:
    """Return a Windows per-user application-data path with a safe fallback."""

    app_data = os.environ.get("APPDATA")
    base = Path(app_data) if app_data else Path.home() / ".videotext"
    return base / "VideoText" / "preferences.json" if app_data else base / "preferences.json"


def _preferences_from_data(data: object) -> Preferences:
    """Merge valid persisted fields into safe defaults without startup errors."""

    preferences = Preferences()
    if not isinstance(data, dict):
        return preferences

    folder = data.get("default_output_folder")
    if isinstance(folder, str):
        preferences.default_output_folder = folder

    formats = data.get("default_export_formats")
    if isinstance(formats, list):
        valid_formats = [
            format_name
            for format_name in formats
            if format_name in SUPPORTED_EXPORT_FORMATS
        ]
        if valid_formats:
            preferences.default_export_formats = list(dict.fromkeys(valid_formats))

    for field_name in (
        "remember_last_folders",
        "open_output_folder_after_completion",
    ):
        value = data.get(field_name)
        if isinstance(value, bool):
            setattr(preferences, field_name, value)

    recent_sources = data.get("recent_sources")
    if isinstance(recent_sources, list):
        preferences.recent_sources = [
            source for source in recent_sources
            if isinstance(source, str) and source.strip() and not _is_temporary_source(source)
        ][:RECENT_SOURCE_LIMIT]

    for field_name in (
        "last_single_video_folder",
        "last_batch_video_folder",
        "last_batch_folder",
        "last_checkpoint_folder",
        "last_output_folder",
    ):
        value = data.get(field_name)
        if isinstance(value, str):
            setattr(preferences, field_name, value)

    return preferences


def load_preferences(path: Path | None = None) -> Preferences:
    """Load valid persisted settings, falling back safely on any problem."""

    path = path or preferences_path()
    try:
        with path.open(encoding="utf-8") as preferences_file:
            return _preferences_from_data(json.load(preferences_file))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return Preferences()


def save_preferences(preferences: Preferences, path: Path | None = None) -> Path:
    """Atomically save human-readable preferences outside project data."""

    path = path or preferences_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path: Path | None = None

    try:
        with tempfile.NamedTemporaryFile(
            "w",
            encoding="utf-8",
            dir=path.parent,
            delete=False,
        ) as temporary_file:
            json.dump(asdict(preferences), temporary_file, indent=2)
            temporary_file.write("\n")
            temporary_path = Path(temporary_file.name)
        temporary_path.replace(path)
    finally:
        if temporary_path is not None and temporary_path.exists():
            temporary_path.unlink()

    return path


def reset_preferences(path: Path | None = None) -> Preferences:
    """Save and return fresh default preferences."""

    preferences = Preferences()
    save_preferences(preferences, path)
    return preferences


def add_recent_source(preferences: Preferences, source: str) -> None:
    """Remember a user-selected persistent source, newest first and unique."""

    source = source.strip()
    if not source or _is_temporary_source(source):
        return
    normalized = os.path.normcase(os.path.normpath(source)) if "://" not in source else source.casefold()
    existing = [
        item for item in preferences.recent_sources
        if (
            os.path.normcase(os.path.normpath(item)) if "://" not in item else item.casefold()
        ) != normalized
    ]
    preferences.recent_sources = [source, *existing][:RECENT_SOURCE_LIMIT]


def clear_recent_sources(preferences: Preferences) -> None:
    """Forget remembered sources without altering other preferences."""

    preferences.recent_sources = []


def _is_temporary_source(source: str) -> bool:
    """Exclude internal downloaded-video workspaces from user-facing history."""

    return "videotext-download-" in source.lower()


def remember_folder(preferences: Preferences, field_name: str, path: str | Path) -> None:
    """Remember an existing folder only when the user enabled that behavior."""

    if not preferences.remember_last_folders:
        return

    folder = Path(path)
    if folder.is_dir() and hasattr(preferences, field_name):
        setattr(preferences, field_name, str(folder))
        save_preferences(preferences)


def valid_initial_directory(path: str) -> str | None:
    """Return an existing remembered directory, otherwise no initial folder."""

    return path if path and Path(path).is_dir() else None
