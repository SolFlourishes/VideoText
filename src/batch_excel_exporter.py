"""Create one translation workbook containing multiple successful videos."""

import os
from pathlib import Path
import tempfile

from openpyxl import Workbook

from excel_exporter import sanitize_worksheet_name, write_presentation_worksheet
from models import Presentation


def export_batch_excel(
    presentations: list[tuple[str, Presentation]],
    output_path: str | Path,
) -> str:
    """Atomically save one worksheet per presentation, or no workbook at all."""

    if not presentations:
        raise ValueError("A consolidated workbook requires at least one successful video.")

    destination = Path(output_path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary_path: Path | None = None
    workbook = Workbook()
    workbook.remove(workbook.active)
    used_names: set[str] = set()

    try:
        for source_path, presentation in presentations:
            worksheet = workbook.create_sheet(
                sanitize_worksheet_name(Path(source_path).stem, used_names),
            )
            write_presentation_worksheet(worksheet, presentation)

        with tempfile.NamedTemporaryFile(
            suffix=".xlsx", dir=destination.parent, delete=False,
        ) as temporary_file:
            temporary_path = Path(temporary_file.name)
        workbook.save(temporary_path)
        os.replace(temporary_path, destination)
        return str(destination)
    finally:
        if temporary_path is not None and temporary_path.exists():
            temporary_path.unlink()
