"""
text_reconstruction.py

Utilities for reconstructing readable text lines from OCR results.
"""

from models import OCRResult, TextLine


#
# Minimum percentage of vertical overlap required for two OCR
# regions to belong to the same visual text line.
#
MIN_VERTICAL_OVERLAP = 0.40


def vertical_overlap(a: OCRResult, top: float, bottom: float) -> float:
    """
    Return the fractional vertical overlap between an OCR region
    and an existing line.
    """

    overlap = min(a.bottom, bottom) - max(a.top, top)

    if overlap <= 0:
        return 0.0

    return overlap / min(
        a.bottom - a.top,
        bottom - top,
    )


def reconstruct_lines(
    ocr_results: list[OCRResult],
) -> list[TextLine]:
    """
    Groups OCR words into reconstructed text lines.
    """

    if not ocr_results:
        return []

    #
    # Sort by top, then left.
    #
    words = sorted(
        ocr_results,
        key=lambda r: (r.top, r.left),
    )

    grouped_lines: list[list[OCRResult]] = []

    line_tops: list[float] = []

    line_bottoms: list[float] = []

    for word in words:

        assigned = False

        for i in range(len(grouped_lines)):

            if (
                vertical_overlap(
                    word,
                    line_tops[i],
                    line_bottoms[i],
                )
                >= MIN_VERTICAL_OVERLAP
            ):

                grouped_lines[i].append(word)

                line_tops[i] = min(
                    line_tops[i],
                    word.top,
                )

                line_bottoms[i] = max(
                    line_bottoms[i],
                    word.bottom,
                )

                assigned = True
                break

        if not assigned:

            grouped_lines.append([word])

            line_tops.append(word.top)

            line_bottoms.append(word.bottom)

    reconstructed: list[TextLine] = []

    for line in grouped_lines:

        line.sort(key=lambda r: r.left)

        reconstructed.append(
            TextLine(
                text=" ".join(
                    word.text
                    for word in line
                ),
                top=min(word.top for word in line),
                bottom=max(word.bottom for word in line),
                left=min(word.left for word in line),
                right=max(word.right for word in line),
                confidence=sum(
                    word.confidence
                    for word in line
                )
                / len(line),
            )
        )

    return reconstructed