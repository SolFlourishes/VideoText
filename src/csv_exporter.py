"""
csv_exporter.py

Exports reconstructed presentations to CSV.
"""

import csv
from io import StringIO

from models import Presentation


def export_csv(presentation: Presentation) -> str:
    """
    Export one CSV row for each paragraph in presentation order.
    """

    output = StringIO(newline="")
    writer = csv.writer(output)

    writer.writerow([
        "Slide Number",
        "Paragraph Type",
        "Paragraph Text",
    ])

    for slide in presentation.slides:
        for paragraph in slide.paragraphs:
            writer.writerow([
                slide.slide_number,
                paragraph.text_type.name,
                paragraph.text,
            ])

    return output.getvalue()
