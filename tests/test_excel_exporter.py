"""Focused tests for the VideoText translation workbook layout."""

import csv
import re
import sys
import tempfile
from pathlib import Path
import unittest

from openpyxl import load_workbook


sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from csv_exporter import export_csv
from excel_exporter import export_excel
from markdown_exporter import export_markdown
from models import Presentation, Slide, TextLine, TextParagraph, TextType


def text_line(text: str) -> TextLine:
    return TextLine(
        text=text,
        top=0,
        bottom=1,
        left=0,
        right=1,
        confidence=1.0,
    )


class ExcelExporterTests(unittest.TestCase):
    def export_workbook(self, paragraphs: list[TextParagraph]):
        presentation = Presentation(
            metadata={"video_path": "D:/Videos/sample.mp4"},
            slides=[
                Slide(
                    slide_number=7,
                    start_time=0.0,
                    end_time=1.0,
                    paragraphs=paragraphs,
                ),
            ],
        )
        temporary_directory = tempfile.TemporaryDirectory()
        output_path = Path(temporary_directory.name) / "export.xlsx"
        export_excel(presentation, str(output_path))
        self.addCleanup(temporary_directory.cleanup)
        return load_workbook(output_path).active

    def test_title_and_editable_metadata_fields(self):
        worksheet = self.export_workbook([])

        self.assertEqual(worksheet["A1"].value, "VideoText Translation Workbook")
        self.assertEqual(
            {str(cell_range) for cell_range in worksheet.merged_cells.ranges},
            {"A1:C1", "B2:C2", "B3:C3", "B4:C4", "B5:C5", "B6:C6", "B7:C7", "B8:C8"},
        )
        self.assertEqual(worksheet["A2"].value, "Video:")
        self.assertEqual(worksheet["B2"].value, "sample")
        self.assertRegex(worksheet["B3"].value, r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}$")
        self.assertIsNone(worksheet["B4"].value)
        self.assertIsNone(worksheet["B5"].value)
        self.assertIsNone(worksheet["B6"].value)
        self.assertIsNone(worksheet["B7"].value)
        self.assertIsNone(worksheet["B8"].value)

    def test_table_headers_freeze_panes_and_filter(self):
        worksheet = self.export_workbook([])

        self.assertEqual(
            [worksheet.cell(row=10, column=column).value for column in range(1, 4)],
            ["Slide", "Original Text", "Translated Text"],
        )
        self.assertEqual(worksheet.freeze_panes, "A11")
        self.assertEqual(worksheet.auto_filter.ref, "A10:C10")
        self.assertTrue(worksheet["A10"].font.bold)
        self.assertTrue(worksheet["A10"].alignment.wrap_text)
        self.assertEqual(worksheet["A10"].alignment.vertical, "center")

    def test_original_text_is_preserved_and_translation_is_blank(self):
        original = "One line"
        worksheet = self.export_workbook([
            TextParagraph(original, text_type=TextType.BODY),
        ])

        self.assertEqual(worksheet["A11"].value, 7)
        self.assertEqual(worksheet["B11"].value, original)
        self.assertIsNone(worksheet["C11"].value)
        self.assertTrue(worksheet["B11"].alignment.wrap_text)
        self.assertEqual(worksheet["B11"].alignment.vertical, "top")
        self.assertTrue(worksheet["C11"].alignment.wrap_text)
        self.assertEqual(worksheet["C11"].alignment.vertical, "top")

    def test_multiline_original_text_and_row_height_are_preserved(self):
        lines = [
            "7. Consider various levels of integration",
            "The religiousness or spirituality of client",
            "The desire of the client to integrate spirituality",
            "The nature of presenting problem",
        ]
        worksheet = self.export_workbook([
            TextParagraph(
                " ".join(lines),
                lines=[text_line(line) for line in lines],
                text_type=TextType.NUMBERED,
            ),
            TextParagraph("One line", text_type=TextType.BODY),
        ])

        self.assertEqual(
            worksheet["B11"].value,
            "\n".join([
                lines[0],
                f"• {lines[1]}",
                f"• {lines[2]}",
                f"• {lines[3]}",
            ]),
        )
        self.assertGreater(worksheet.row_dimensions[11].height, worksheet.row_dimensions[12].height)
        self.assertIsNone(worksheet["C11"].value)

    def test_existing_bullet_markers_are_not_duplicated(self):
        paragraph = TextParagraph(
            "Heading\n• existing\n- dash\n◦ circle",
            text_type=TextType.BODY,
        )
        worksheet = self.export_workbook([paragraph])

        self.assertEqual(
            worksheet["B11"].value,
            "Heading\n• existing\n- dash\n◦ circle",
        )

    def test_markdown_and_csv_exports_remain_unchanged(self):
        presentation = Presentation(slides=[
            Slide(
                slide_number=1,
                start_time=0.0,
                end_time=1.0,
                paragraphs=[TextParagraph("Hello", text_type=TextType.BODY)],
            ),
        ])

        with tempfile.TemporaryDirectory() as temporary_directory:
            output = Path(temporary_directory)
            markdown_path = output / "export.md"
            csv_path = output / "export.csv"
            export_markdown(presentation, str(markdown_path))
            export_csv(presentation, str(csv_path))

            self.assertEqual(
                markdown_path.read_text(encoding="utf-8"),
                "# VideoText Export\n\n# Slide 1\n\nHello\n",
            )
            with csv_path.open(encoding="utf-8", newline="") as file:
                self.assertEqual(list(csv.reader(file)), [
                    ["Slide Number", "Paragraph Type", "Paragraph Text"],
                    ["1", "BODY", "Hello"],
                ])


if __name__ == "__main__":
    unittest.main()
