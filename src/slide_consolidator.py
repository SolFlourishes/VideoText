"""
slide_consolidator.py

Groups CandidateFrames into logical slides.
"""

from copy import deepcopy
from difflib import SequenceMatcher
from typing import List

from models import CandidateFrame, Slide, SlideBuild


SIMILARITY_THRESHOLD = 0.60

#
# Paragraphs at this level may differ by a few OCR characters or by
# accidental spacing within a word.  This threshold still requires most
# characters to agree, while allowing variants such as "based" / "basec s".
#
PARAGRAPH_SIMILARITY_THRESHOLD = 0.65


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
        progressive_endpoint = _progressive_prefix_endpoint(self.paragraphs)

        if progressive_endpoint is not None:
            return progressive_endpoint

        #
        # Prefer the text observed most often across frames.  OCR variants
        # remain as separate observations, so their normalized text is the
        # unit counted here.
        #
        counts: dict[str, int] = {}

        for paragraph in self.paragraphs:
            text = normalize_text(paragraph.text)
            counts[text] = counts.get(text, 0) + 1

        #
        # On equal observation counts, retain the more complete text.  dict
        # insertion order plus max()'s first-match behavior preserves the
        # existing deterministic ordering when both values are tied.
        #
        selected_text = max(
            counts,
            key=lambda text: (counts[text], len(text)),
        )

        # Return the first original Paragraph for the selected text.
        return next(
            paragraph
            for paragraph in self.paragraphs
            if normalize_text(paragraph.text) == selected_text
        )


def _progressive_prefix_endpoint(paragraphs):
    """
    Return the longest original paragraph when all variants form one strict
    prefix-extension chain; otherwise return None.
    """

    variants: dict[str, None] = {}

    for paragraph in paragraphs:
        variants.setdefault(normalize_text(paragraph.text), None)

    ordered_variants = sorted(variants, key=len)

    if len(ordered_variants) < 2:
        return None

    if not all(
        len(shorter) < len(longer)
        and longer.startswith(shorter)
        for shorter, longer in zip(
            ordered_variants,
            ordered_variants[1:],
        )
    ):
        return None

    endpoint = ordered_variants[-1]

    # Return the stored original object rather than normalized text.
    return next(
        paragraph
        for paragraph in paragraphs
        if normalize_text(paragraph.text) == endpoint
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


def paragraph_similarity_score(text1: str, text2: str) -> float:
    """
    Compute character-level similarity for OCR variants of one paragraph.

    Word-set similarity is appropriate for deciding whether whole frames
    belong to one slide, but it loses the spelling and spacing detail needed
    to compare individual paragraphs.  Character similarity preserves that
    detail and is deterministic.
    """

    return SequenceMatcher(
        None,
        normalize_text(text1),
        normalize_text(text2),
        autojunk=False,
    ).ratio()


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

        #
        # Near-identical OCR variants.  This handles small substitutions,
        # insertions, and spacing differences without changing OCR text.
        #
        if (
            paragraph_similarity_score(existing_text, candidate_text)
            >= PARAGRAPH_SIMILARITY_THRESHOLD
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

            #
            # Each frame is an OCR observation of this build.  Preserve all
            # of that evidence for paragraph clustering rather than using
            # only the first frame selected for reporting.
            #
            for frame in build.candidate_frames:

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
