"""
excel_exporter.py

Exports reconstructed presentations to Excel.
"""

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from datetime import datetime
from math import ceil
from pathlib import Path

from models import Presentation


BASE_ROW_HEIGHT = 15
MIN_CONTENT_ROW_HEIGHT = 15
MAX_CONTENT_ROW_HEIGHT = 300
TEXT_COLUMN_WIDTH = 60
HEADER_ROW_HEIGHT = 20
BULLET_PREFIXES = ("•", "-", "◦", "▪", "○", "*")
TITLE_ROW = 1
METADATA_START_ROW = 2
TABLE_HEADER_ROW = 10
TABLE_START_ROW = TABLE_HEADER_ROW + 1
TITLE_TEXT = "VideoText Translation Workbook"
TABLE_HEADERS = ("Slide", "Original Text", "Translated Text")
HEADER_FILL = PatternFill(fill_type="solid", fgColor="D9EAF7")


def _paragraph_lines(paragraph) -> list[str]:
    """Return visual source lines when available, otherwise text lines."""

    source_lines = [line.text for line in paragraph.lines]

    if sum(bool(line.strip()) for line in source_lines) > 1:
        return source_lines

    return paragraph.text.splitlines()


def _format_paragraph_text(paragraph) -> tuple[str, int]:
    """Format continuation lines for one readable spreadsheet cell."""

    lines = _paragraph_lines(paragraph)

    if sum(bool(line.strip()) for line in lines) < 2:
        return paragraph.text, 1

    formatted_lines: list[str] = []
    first_content_line = True

    for line in lines:
        if not line.strip():
            formatted_lines.append(line)
            continue

        if first_content_line:
            formatted_lines.append(line)
            first_content_line = False
        elif line.lstrip().startswith(BULLET_PREFIXES):
            formatted_lines.append(line)
        else:
            formatted_lines.append(f"• {line}")

    return "\n".join(formatted_lines), max(1, len(formatted_lines))


def _estimate_wrapped_lines(text: str, column_width: float) -> int:
    """Estimate visible Excel lines from explicit breaks and bounded width."""
    characters_per_line = max(1, int(column_width))
    lines = text.splitlines() or [""]
    return sum(max(1, ceil(len(line) / characters_per_line)) for line in lines)


def _estimate_row_height(*cell_texts: str) -> float:
    """Return a bounded height for the most demanding wrapped cell in a row."""
    visible_lines = max(
        _estimate_wrapped_lines(text, TEXT_COLUMN_WIDTH)
        for text in cell_texts
    )
    return min(
        MAX_CONTENT_ROW_HEIGHT,
        max(MIN_CONTENT_ROW_HEIGHT, BASE_ROW_HEIGHT * visible_lines),
    )


def _video_name(presentation: Presentation) -> str:
    """Return the processed video stem when metadata makes it available."""

    video_path = presentation.metadata.get("video_path")
    if video_path:
        return Path(str(video_path)).stem

    checkpoint_path = presentation.metadata.get("source_checkpoint")
    if checkpoint_path:
        checkpoint = Path(str(checkpoint_path))
        if checkpoint.parent.name.lower() == "cache":
            return checkpoint.parent.parent.name

    return ""


def _write_metadata(worksheet, presentation: Presentation) -> None:
    """Write editable translation metadata above the slide table."""

    worksheet.merge_cells("A1:C1")
    title_cell = worksheet.cell(row=TITLE_ROW, column=1, value=TITLE_TEXT)
    title_cell.font = Font(bold=True, size=16)
    title_cell.alignment = Alignment(vertical="center")
    worksheet.row_dimensions[TITLE_ROW].height = 24

    metadata = (
        ("Video:", _video_name(presentation)),
        ("Date (Processed):", datetime.now().strftime("%Y-%m-%d %H:%M")),
        ("Date (Translated):", ""),
        ("Translator(s):", ""),
        ("Language (Source):", ""),
        ("Language (Target):", ""),
        ("Notes:", ""),
    )

    for offset, (label, value) in enumerate(metadata):
        row = METADATA_START_ROW + offset
        worksheet.cell(row=row, column=1, value=label).font = Font(bold=True)
        worksheet.merge_cells(start_row=row, start_column=2, end_row=row, end_column=3)
        value_cell = worksheet.cell(row=row, column=2, value=value)
        value_cell.alignment = Alignment(wrap_text=True, vertical="top")

    worksheet.row_dimensions[METADATA_START_ROW + len(metadata) - 1].height = 36


def export_excel(
    presentation: Presentation,
    output_path: str,
) -> str:
    """
    Export one worksheet row for each paragraph in presentation order.
    """

    workbook = Workbook()
    worksheet = workbook.active

    _write_metadata(worksheet, presentation)

    for column, header in enumerate(TABLE_HEADERS, start=1):
        cell = worksheet.cell(row=TABLE_HEADER_ROW, column=column, value=header)
        cell.font = Font(bold=True)
        cell.fill = HEADER_FILL
        cell.alignment = Alignment(wrap_text=True, vertical="center")

    worksheet.row_dimensions[TABLE_HEADER_ROW].height = HEADER_ROW_HEIGHT

    worksheet.freeze_panes = f"A{TABLE_START_ROW}"

    for slide in presentation.slides:
        for paragraph in slide.paragraphs:
            paragraph_text, _line_count = _format_paragraph_text(paragraph)

            row_number = worksheet.max_row + 1
            worksheet.cell(row=row_number, column=1, value=slide.slide_number)
            original_text_cell = worksheet.cell(
                row=row_number,
                column=2,
                value=paragraph_text,
            )
            original_text_cell.alignment = Alignment(
                wrap_text=True,
                vertical="top",
            )
            translated_text_cell = worksheet.cell(row=row_number, column=3, value="")
            translated_text_cell.alignment = Alignment(
                wrap_text=True,
                vertical="top",
            )
            worksheet.row_dimensions[row_number].height = _estimate_row_height(
                paragraph_text,
                "",
            )

    worksheet.column_dimensions["A"].width = 10
    worksheet.column_dimensions["B"].width = TEXT_COLUMN_WIDTH
    worksheet.column_dimensions["C"].width = TEXT_COLUMN_WIDTH
    worksheet.auto_filter.ref = f"A{TABLE_HEADER_ROW}:C{worksheet.max_row}"

    workbook.save(output_path)

    return output_path
