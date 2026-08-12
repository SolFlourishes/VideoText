"""Small, privacy-conscious diagnostics for unexpected packaged GUI failures."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
import re


_SECRET_PATTERNS = (
    re.compile(r"sk-[A-Za-z0-9_-]+"),
    re.compile(r"(?i)(api[_ -]?key\s*[=:]\s*)[^\s,;]+"),
)


def gui_diagnostic_log_path() -> Path:
    """Return the user-writable log location used by the packaged GUI."""

    return Path.home() / "AppData" / "Local" / "VideoText" / "logs" / "workflow.log"


def _redact(value: str) -> str:
    """Remove common credential forms before a diagnostic is persisted."""

    redacted = value
    for pattern in _SECRET_PATTERNS:
        redacted = pattern.sub(r"\1[redacted]" if pattern.groups else "[redacted]", redacted)
    return redacted


def write_gui_diagnostic(event: str, detail: str = "") -> Path | None:
    """Append one resilient, sanitized lifecycle event; never mask the cause."""

    try:
        path = gui_diagnostic_log_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().isoformat(timespec="seconds")
        with path.open("a", encoding="utf-8") as log:
            log.write(f"{timestamp} | {event} | {_redact(detail)}\n")
        return path
    except OSError:
        return None
