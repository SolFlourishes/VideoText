"""
paragraph_reconstruction.py

Reconstruct logical paragraphs from visual text lines.
"""

from models import CandidateFrame, TextParagraph, TextType


#
# If a BODY line begins this many pixels farther left than the
# previous line, assume OCR missed a bullet following a numbered item.
#
LEFT_SHIFT_THRESHOLD = 100

#
# If two BODY lines begin within this many pixels of each other,
# they are considered peers rather than a wrapped continuation.
#
BODY_ALIGNMENT_THRESHOLD = 15


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
        # Inferred bullet after a numbered item.
        #
        if (
            current.text_type == TextType.NUMBERED
            and line.text_type == TextType.BODY
            and previous_line is not None
            and line.left < (previous_line.left - LEFT_SHIFT_THRESHOLD)
        ):

            frame.text_paragraphs.append(current)

            current = TextParagraph(
                text=line.text,
                lines=[line],
                text_type=TextType.BULLET,
                indent_level=line.indent_level,
                bullet_level=line.bullet_level,
            )

            previous_line = line
            continue

        #
        # Consecutive inferred bullets.
        #
        if (
            current.text_type == TextType.BULLET
            and line.text_type == TextType.BODY
            and previous_line is not None
            and abs(line.left - previous_line.left)
                <= BODY_ALIGNMENT_THRESHOLD
        ):

            frame.text_paragraphs.append(current)

            current = TextParagraph(
                text=line.text,
                lines=[line],
                text_type=TextType.BULLET,
                indent_level=line.indent_level,
                bullet_level=line.bullet_level,
            )

            previous_line = line
            continue

        #
        # Continue current paragraph.
        #
        current.text += " " + line.text.strip()
        current.lines.append(line)

        previous_line = line

    #
    # Flush final paragraph.
    #
    if current is not None:
        frame.text_paragraphs.append(current)