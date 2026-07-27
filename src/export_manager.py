"""
export_manager.py

Coordinates presentation exports and their output paths.
"""

from pathlib import Path

from csv_exporter import export_csv
from excel_exporter import export_excel
from markdown_exporter import export_markdown
from models import Presentation


EXPORTERS = {
    "markdown": (".md", export_markdown),
    "csv": (".csv", export_csv),
    "excel": (".xlsx", export_excel),
}


def export_all(
    presentation: Presentation,
    output_directory: Path,
    formats: list[str],
) -> dict[str, str]:
    """
    Export a presentation in each requested format.
    """

    output_directory.mkdir(parents=True, exist_ok=True)

    saved_paths: dict[str, str] = {}

    for format_name in formats:
        if format_name not in EXPORTERS:
            raise ValueError(f"Unsupported export format: {format_name}")

        extension, exporter = EXPORTERS[format_name]
        output_path = output_directory / f"videotext_export{extension}"

        saved_paths[format_name] = exporter(
            presentation,
            output_path.as_posix(),
        )

    return saved_paths
