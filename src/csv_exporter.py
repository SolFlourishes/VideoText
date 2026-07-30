"""
csv_exporter.py

Exports reconstructed presentations to CSV.
"""

import csv
from pathlib import Path

from models import Presentation


def export_csv(
    presentation: Presentation,
    output_path: str,
) -> str:
    """
    Export one CSV row for each paragraph in presentation order.
    """

    with Path(output_path).open(
        "w",
        encoding="utf-8",
        newline="",
    ) as output:
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

    return output_path
