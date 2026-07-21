"""
slide_compare.py

Utilities for comparing two reconstructed slides.
"""

from models import CandidateFrame, ComparisonResult


def normalize(text: str) -> str:
    """
    Normalize text for comparison.
    """
    return " ".join(text.lower().split())


def compare_frames(
    previous: CandidateFrame,
    current: CandidateFrame,
) -> ComparisonResult:
    """
    Compare two candidate frames using reconstructed text lines.
    """

    previous_lines = [
        normalize(line.text)
        for line in previous.text_lines
        if line.text.strip()
    ]

    current_lines = [
        normalize(line.text)
        for line in current.text_lines
        if line.text.strip()
    ]

    previous_set = set(previous_lines)
    current_set = set(current_lines)

    shared = sorted(previous_set & current_set)
    added = sorted(current_set - previous_set)
    removed = sorted(previous_set - current_set)

    total = len(previous_set | current_set)

    similarity = (
        len(shared) / total
        if total > 0
        else 1.0
    )

    result = ComparisonResult()

    result.shared_lines = shared
    result.added_lines = added
    result.removed_lines = removed
    result.similarity = similarity

    #
    # Progressive build
    #
    if (
        len(removed) == 0
        and len(shared) == len(previous_set)
    ):
        result.decision = True
        result.reason = "Previous slide is a subset of the current slide."

    #
    # Exact duplicate
    #
    elif (
        len(added) == 0
        and len(removed) == 0
    ):
        result.decision = True
        result.reason = "Slides are identical."

    #
    # New slide
    #
    else:
        result.decision = False
        result.reason = "Slide content changed."

    return result