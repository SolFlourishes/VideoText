"""
slide_consolidator.py

Groups CandidateFrames into logical slides.
"""

from copy import deepcopy
from typing import List

from models import CandidateFrame, Slide, SlideBuild


SIMILARITY_THRESHOLD = 0.60


class ParagraphCluster:
    """
    Collect multiple observations of the same paragraph.
    """

    def __init__(self, paragraph):
        self.paragraphs = [deepcopy(paragraph)]

    def add(self, paragraph):
        self.paragraphs.append(deepcopy(paragraph))

    @property
    def best(self):
        return max(
            self.paragraphs,
            key=lambda p: len(normalize_text(p.text)),
        )


def normalize_text(text: str) -> str:
    """
    Normalize OCR text for comparison.
    """
    return " ".join(text.lower().split())


def text_words(text: str) -> set[str]:
    """
    Convert text into a normalized set of words.
    """
    return set(normalize_text(text).split())


def similarity_score(text1: str, text2: str) -> float:
    """
    Compute Jaccard similarity between two texts.
    """

    words1 = text_words(text1)
    words2 = text_words(text2)

    if not words1 and not words2:
        return 1.0

    if not words1 or not words2:
        return 0.0

    intersection = len(words1 & words2)
    union = len(words1 | words2)

    return intersection / union


def find_matching_paragraph(paragraphs, candidate):
    """
    Return the index of a matching paragraph, or None.
    """

    candidate_text = normalize_text(candidate.text)

    for index, paragraph in enumerate(paragraphs):

        if paragraph.text_type != candidate.text_type:
            continue

        existing_text = normalize_text(paragraph.text)

        #
        # Exact duplicate.
        #
        if existing_text == candidate_text:
            return index

        #
        # One paragraph is a prefix of the other.
        #
        if (
            candidate_text.startswith(existing_text)
            or existing_text.startswith(candidate_text)
        ):
            return index

    return None


def merge_or_add_paragraph(paragraphs, candidate):
    """
    Add a paragraph or replace an existing one with a more complete version.
    """

    candidate_text = normalize_text(candidate.text)

    match = find_matching_paragraph(
        paragraphs,
        candidate,
    )

    if match is None:
        paragraphs.append(deepcopy(candidate))
        return

    index = match
    paragraph = paragraphs[index]
    existing_text = normalize_text(paragraph.text)

    #
    # Exact duplicate.
    #
    if existing_text == candidate_text:
        return

    #
    # Candidate is more complete.
    #
    if (
        candidate_text.startswith(existing_text)
        and len(candidate_text) > len(existing_text)
    ):
        paragraphs[index] = deepcopy(candidate)
        return

    #
    # Existing paragraph is already more complete.
    #
    if (
        existing_text.startswith(candidate_text)
        and len(existing_text) >= len(candidate_text)
    ):
        return

    #
    # Fallback (should rarely occur).
    #
    paragraphs.append(deepcopy(candidate))


def is_same_slide(previous_text: str, current_text: str) -> bool:
    """
    Determine whether two frames belong to the same slide.
    """

    previous = normalize_text(previous_text)
    current = normalize_text(current_text)

    #
    # Exact duplicate.
    #
    if previous == current:
        return True

    #
    # Progressive build.
    #
    if current.startswith(previous):
        return True

    #
    # Word similarity.
    #
    return similarity_score(previous, current) >= SIMILARITY_THRESHOLD


def consolidate_slides(candidate_frames: List[CandidateFrame]) -> List[Slide]:
    """
    Consolidate candidate frames into logical slides.
    """

    if not candidate_frames:
        return []

    slides: List[Slide] = []

    slide_number = 1

    first_frame = candidate_frames[0]

    first_build = SlideBuild(
        candidate_frames=[first_frame],
        final_text=first_frame.combined_text,
    )

    current_slide = Slide(
        slide_number=slide_number,
        start_time=first_frame.timestamp,
        end_time=first_frame.timestamp,
        builds=[first_build],
        final_text=first_frame.combined_text,
    )

    slides.append(current_slide)

    current_build = first_build

    for frame in candidate_frames[1:]:

        if is_same_slide(
            current_slide.final_text,
            frame.combined_text,
        ):

            if normalize_text(frame.combined_text) == normalize_text(
                current_build.final_text
            ):

                current_build.candidate_frames.append(frame)

            else:

                current_build = SlideBuild(
                    candidate_frames=[frame],
                    final_text=frame.combined_text,
                )

                current_slide.builds.append(current_build)

                current_slide.final_text = frame.combined_text

            current_slide.end_time = frame.timestamp

        else:

            slide_number += 1

            current_build = SlideBuild(
                candidate_frames=[frame],
                final_text=frame.combined_text,
            )

            current_slide = Slide(
                slide_number=slide_number,
                start_time=frame.timestamp,
                end_time=frame.timestamp,
                builds=[current_build],
                final_text=frame.combined_text,
            )

            slides.append(current_slide)

    #
    # Build canonical paragraphs.
    #
    for slide in slides:

        clusters: list[ParagraphCluster] = []

        for build in slide.builds:

            frame = build.representative_frame

            for paragraph in frame.text_paragraphs:

                match = find_matching_paragraph(
                    [cluster.best for cluster in clusters],
                    paragraph,
                )

                if match is None:
                    clusters.append(ParagraphCluster(paragraph))
                else:
                    clusters[match].add(paragraph)

        slide.paragraphs.clear()

        for cluster in clusters:
            slide.paragraphs.append(cluster.best)

    return slides