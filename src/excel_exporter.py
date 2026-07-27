"""
excel_exporter.py

Exports reconstructed presentations to Excel.
"""

from openpyxl import Workbook
from openpyxl.styles import Font
from openpyxl.utils import get_column_letter

from models import Presentation


def export_excel(
    presentation: Presentation,
    output_path: str,
) -> str:
    """
    Export one worksheet row for each paragraph in presentation order.
    """

    workbook = Workbook()
    worksheet = workbook.active

    worksheet.append([
        "Slide Number",
        "Paragraph Type",
        "Paragraph Text",
    ])

    for cell in worksheet[1]:
        cell.font = Font(bold=True)

    worksheet.freeze_panes = "A2"

    for slide in presentation.slides:
        for paragraph in slide.paragraphs:
            worksheet.append([
                slide.slide_number,
                paragraph.text_type.name,
                paragraph.text,
            ])

    for column_cells in worksheet.columns:
        max_length = max(
            len(str(cell.value)) if cell.value is not None else 0
            for cell in column_cells
        )
        column_letter = get_column_letter(column_cells[0].column)
        worksheet.column_dimensions[column_letter].width = max_length + 2

    workbook.save(output_path)

    return output_path
