"""
paragraph_reconstruction.py

Reconstruct logical paragraphs from visual text lines.
"""

from models import CandidateFrame, TextParagraph, TextType


def reconstruct_paragraphs(frame: CandidateFrame) -> None:
    """
    Build logical paragraphs from reconstructed text lines.

    Updates frame.text_paragraphs.
    """

    frame.text_paragraphs.clear()

    if not frame.text_lines:
        return

    current = None
    previous_line = None

    for line in frame.text_lines:

        #
        # Explicit paragraph starters.
        #
        if line.text_type in (
            TextType.TITLE,
            TextType.NUMBERED,
            TextType.BULLET,
            TextType.SUB_BULLET,
        ):

            if current is not None:
                frame.text_paragraphs.append(current)

            current = TextParagraph(
                text=line.text,
                lines=[line],
                text_type=line.text_type,
                indent_level=line.indent_level,
                bullet_level=line.bullet_level,
            )

            previous_line = line
            continue

        #
        # First BODY paragraph.
        #
        if current is None:

            current = TextParagraph(
                text=line.text,
                lines=[line],
                text_type=line.text_type,
                indent_level=line.indent_level,
                bullet_level=line.bullet_level,
            )

            previous_line = line
            continue

        #
        # Preserve BODY as a continuation.  A new bullet must be identified
        # by structure detection rather than inferred from indentation alone.
        #
        current.text += " " + line.text.strip()
        current.lines.append(line)

        previous_line = line

    #
    # Flush final paragraph.
    #
    if current is not None:
        frame.text_paragraphs.append(current)
