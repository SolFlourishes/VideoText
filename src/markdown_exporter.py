"""
markdown_exporter.py

Exports reconstructed slides to Markdown.
"""

from pathlib import Path

from models import Presentation


def export_markdown(
    presentation: Presentation,
    output_path: str,
) -> str:
    """
    Export a presentation to a Markdown file.
    """

    output: list[str] = []

    output.append("# VideoText Export")
    output.append("")

    for slide in presentation.slides:

        output.append(f"# Slide {slide.slide_number}")
        output.append("")

        for paragraph in slide.paragraphs:

            text = paragraph.text.strip()

            if not text:
                continue

            match paragraph.text_type.name:

                case "TITLE":
                    output.append(f"## {text}")

                case "NUMBERED":
                    output.append(text)

                case "BULLET":
                    output.append(f"- {text}")

                case _:
                    output.append(text)

            output.append("")

    markdown = "\n".join(output)

    Path(output_path).write_text(markdown, encoding="utf-8")

    return output_path
