"""
export_manager.py

Coordinates presentation exports and their output paths.
"""

from pathlib import Path

from csv_exporter import export_csv
from excel_exporter import export_excel
from markdown_exporter import export_markdown
from models import CandidateFrame, Presentation
from ocr_confidence_stats import (
    DocumentOCRConfidenceStats,
    calculate_document_ocr_confidence_stats,
)


EXPORTERS = {
    "markdown": (".md", export_markdown),
    "csv": (".csv", export_csv),
    "excel": (".xlsx", export_excel),
}


def export_all(
    presentation: Presentation,
    output_directory: Path,
    formats: list[str],
    output_stem: str,
    progress_callback=None,
    candidate_frames: list[CandidateFrame] | None = None,
    ocr_confidence_statistics: DocumentOCRConfidenceStats | None = None,
) -> dict[str, str]:
    """
    Export a presentation in each requested format.
    """

    output_directory.mkdir(parents=True, exist_ok=True)

    saved_paths: dict[str, str] = {}
    # Preserve the older optional frame context while accepting statistics
    # already calculated by the shared processing service.  Either path keeps
    # the result transient rather than storing it on Presentation.
    if ocr_confidence_statistics is None and candidate_frames is not None:
        ocr_confidence_statistics = calculate_document_ocr_confidence_stats(
            candidate_frames
        )

    for index, format_name in enumerate(formats, start=1):
        if format_name not in EXPORTERS:
            raise ValueError(f"Unsupported export format: {format_name}")

        extension, exporter = EXPORTERS[format_name]
        output_path = output_directory / f"{output_stem}{extension}"

        try:
            if format_name == "csv":
                saved_paths[format_name] = exporter(
                    presentation,
                    output_path.as_posix(),
                    ocr_confidence_statistics,
                )
            else:
                saved_paths[format_name] = exporter(
                    presentation,
                    output_path.as_posix(),
                )
        except PermissionError as error:
            format_label = format_name.upper()
            raise PermissionError(
                f"Could not write {format_label} because the file is open "
                f"or locked:\n{output_path}\n"
                "Close the file and run VideoText again."
            ) from error

        if progress_callback is not None:
            progress_callback(index, len(formats))

    return saved_paths
