"""
slide_consolidator.py

Groups CandidateFrames into logical slides.
"""

from typing import List

from models import CandidateFrame, Slide, SlideBuild


def normalize_text(text: str) -> str:
    """
    Normalize OCR text for comparison.
    """
    return " ".join(text.lower().split())


def is_same_slide(previous_text: str, current_text: str) -> bool:
    """
    Determine whether two frames belong to the same logical slide.
    """

    previous = normalize_text(previous_text)
    current = normalize_text(current_text)

    #
    # Exact duplicate.
    #
    if current == previous:
        return True

    #
    # Progressive build.
    #
    if current.startswith(previous):
        return True

    return False


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

    #
    # Track the current build separately.
    #
    current_build = first_build

    for frame in candidate_frames[1:]:

        #
        # Same slide.
        #
        if is_same_slide(
            current_slide.final_text,
            frame.combined_text,
        ):

            #
            # Same build (identical text).
            #
            if normalize_text(frame.combined_text) == normalize_text(current_build.final_text):

                current_build.candidate_frames.append(frame)

            #
            # Progressive build.
            #
            else:

                current_build = SlideBuild(
                    candidate_frames=[frame],
                    final_text=frame.combined_text,
                )

                current_slide.builds.append(current_build)

                current_slide.final_text = frame.combined_text

            current_slide.end_time = frame.timestamp

        #
        # New slide.
        #
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

    return slides