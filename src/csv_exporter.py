"""
csv_exporter.py

Exports reconstructed presentations to CSV.
"""

import csv
from math import isfinite
from pathlib import Path

from models import Presentation
from ocr_confidence_stats import DocumentOCRConfidenceStats


CONFIDENCE_STATISTICS_FIELDS = (
    "ocr_region_count",
    "ocr_confidence_minimum",
    "ocr_confidence_maximum",
    "ocr_confidence_mean",
    "ocr_confidence_median",
    "ocr_below_threshold_count",
    "ocr_below_threshold_proportion",
    "ocr_confidence_threshold",
)


def _export_statistic_value(value: float | int | None) -> float | int | str:
    """Return a CSV-safe descriptive value without introducing NaN text."""

    if value is None:
        return ""
    if isinstance(value, float) and not isfinite(value):
        return ""
    return value


def _confidence_statistics_row(
    statistics: DocumentOCRConfidenceStats,
) -> list[float | int | str]:
    """Format pre-calculated document confidence statistics for CSV rows."""

    return [
        statistics.region_count,
        _export_statistic_value(statistics.minimum),
        _export_statistic_value(statistics.maximum),
        _export_statistic_value(statistics.mean),
        _export_statistic_value(statistics.median),
        statistics.below_threshold_count,
        _export_statistic_value(statistics.below_threshold_proportion),
        _export_statistic_value(statistics.threshold),
    ]


def export_csv(
    presentation: Presentation,
    output_path: str,
    ocr_confidence_statistics: DocumentOCRConfidenceStats | None = None,
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

        headers = [
            "Slide Number",
            "Paragraph Type",
            "Paragraph Text",
        ]
        if ocr_confidence_statistics is not None:
            # Append descriptive document-level fields so existing CSV columns
            # retain their names, order, and meaning for legacy consumers.
            headers.extend(CONFIDENCE_STATISTICS_FIELDS)
        writer.writerow(headers)

        confidence_row = (
            _confidence_statistics_row(ocr_confidence_statistics)
            if ocr_confidence_statistics is not None
            else []
        )

        for slide in presentation.slides:
            for paragraph in slide.paragraphs:
                row = [
                    slide.slide_number,
                    paragraph.text_type.name,
                    paragraph.text,
                ]
                writer.writerow(row + confidence_row)

    return output_path
