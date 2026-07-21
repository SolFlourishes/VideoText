"""
structure_detection.py

Assign structural meaning to reconstructed text lines.

Uses slide geometry rather than OCR characters whenever possible.
"""

from models import CandidateFrame, TextType


BULLET_PREFIXES = (
    "•",
    "-",
    "*",
    "▪",
    "◦",
    "○",
)

NUMBER_PREFIXES = tuple(f"{i}." for i in range(1, 100))


def is_numbered(text: str) -> bool:
    """Return True if the text begins with a numbered list marker."""
    return text.startswith(NUMBER_PREFIXES)


def is_bullet(text: str) -> bool:
    """Return True if the text begins with a bullet marker."""
    return text.startswith(BULLET_PREFIXES)


def detect_structure(frame: CandidateFrame) -> None:
    """
    Analyze reconstructed text lines and assign structure.

    Updates TextLine objects in-place.
    """

    if not frame.text_lines:
        return

    min_left = min(line.left for line in frame.text_lines)

    slide_left = min(line.left for line in frame.text_lines)
    slide_right = max(line.right for line in frame.text_lines)
    slide_center = (slide_left + slide_right) / 2

    previous_line = None

    for index, line in enumerate(frame.text_lines):

        text = line.text.strip()

        line.text_type = TextType.BODY
        line.indent_level = 0
        line.bullet_level = 0

        #
        # Explicit numbered item.
        #
        if is_numbered(text):
            line.text_type = TextType.NUMBERED
            previous_line = line
            continue

        #
        # Explicit bullet.
        #
        if is_bullet(text):
            line.text_type = TextType.BULLET

            indent = line.left - min_left
            if indent > 40:
                line.indent_level = 1
                line.bullet_level = 1

            previous_line = line
            continue

        #
        # Continuation detection.
        #
        if previous_line is not None:

            indent = line.left - previous_line.left

            #
            # Slightly indented wrapped text is usually a continuation.
            #
            if -15 <= indent <= 60:
                line.text_type = TextType.BODY
                previous_line = line
                continue

        #
        # Possible title.
        #
        center = (line.left + line.right) / 2
        centered = abs(center - slide_center) < 40

        if index == 0 and (centered or len(text) < 60):
            line.text_type = TextType.TITLE

        previous_line = line