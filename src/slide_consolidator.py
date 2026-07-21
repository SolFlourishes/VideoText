"""
slide_consolidator.py

Groups CandidateFrames into logical slides.

This module is responsible for determining where one slide ends
and the next begins. The initial implementation simply creates
one Slide per CandidateFrame. Future versions will merge frames
into logical slides and detect progressive builds.
"""

from typing import List

from models import CandidateFrame, Slide, SlideBuild


def consolidate_slides(candidate_frames: List[CandidateFrame]) -> List[Slide]:
    """
    Convert candidate frames into Slide objects.

    Initial implementation:
    - One CandidateFrame becomes one Slide.
    - No consolidation is performed yet.
    """

    slides: List[Slide] = []

    for index, frame in enumerate(candidate_frames, start=1):
        build = SlideBuild(candidate_frame=frame)

        slide = Slide(
            slide_number=index,
            start_time=frame.timestamp,
            end_time=frame.timestamp,
            builds=[build],
            final_text=frame.combined_text,
        )

        slides.append(slide)

    return slides