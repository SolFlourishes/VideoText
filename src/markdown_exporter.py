"""
markdown_exporter.py

Exports reconstructed slides to Markdown.
"""

from models import Slide


def export_markdown(slides: list[Slide]) -> str:
    """
    Export slides to Markdown.
    """

    output: list[str] = []

    output.append("# VideoText Export")
    output.append("")

    for slide in slides:

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

    return "\n".join(output)