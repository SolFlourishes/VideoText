"""
frame_analyzer.py

Analyzes a video and identifies candidate frames for OCR.
"""

from image_utils import calculate_frame_difference
from models import CandidateFrame
from config import (
    FRAME_DIFFERENCE_THRESHOLD,
    MAX_SECONDS_BETWEEN_CAPTURES,
)

#
# Number of consecutive "quiet" frames required before
# considering a slide stable.
#
STABLE_FRAMES_REQUIRED = 5


def analyze_video(video, fps):
    """
    Analyze every frame in a video.

    Args:
        video: OpenCV VideoCapture object.
        fps: Frames per second.

    Returns:
        List[CandidateFrame]
    """

    candidate_frames = []

    success, previous_frame = video.read()

    if not success:
        return candidate_frames

    candidate_frames.append(
        CandidateFrame(
            frame_number=0,
            timestamp=0.0,
            image=previous_frame.copy(),
            difference_score=0.0,
        )
    )

    frame_number = 1
    last_saved_frame = 0

    #
    # Tracks an active transition.
    #
    transition_active = False
    stable_count = 0

    pending_frame = None
    pending_frame_number = 0
    pending_timestamp = 0.0
    pending_score = 0.0

    while True:

        success, current_frame = video.read()

        if not success:
            break

        score = calculate_frame_difference(
            previous_frame,
            current_frame,
        )

        seconds_since_last_save = (
            frame_number - last_saved_frame
        ) / fps

        #
        # Transition detected.
        #
        if score >= FRAME_DIFFERENCE_THRESHOLD:

            transition_active = True
            stable_count = 0

            pending_frame = current_frame.copy()
            pending_frame_number = frame_number
            pending_timestamp = frame_number / fps
            pending_score = score

        #
        # Wait until the image has stabilized.
        #
        elif transition_active:

            stable_count += 1

            if stable_count >= STABLE_FRAMES_REQUIRED:

                candidate_frames.append(
                    CandidateFrame(
                        frame_number=pending_frame_number,
                        timestamp=pending_timestamp,
                        image=pending_frame,
                        difference_score=pending_score,
                    )
                )

                last_saved_frame = pending_frame_number

                transition_active = False
                stable_count = 0

        #
        # Long static periods.
        #
        elif (
            seconds_since_last_save
            >= MAX_SECONDS_BETWEEN_CAPTURES
        ):

            candidate_frames.append(
                CandidateFrame(
                    frame_number=frame_number,
                    timestamp=frame_number / fps,
                    image=current_frame.copy(),
                    difference_score=score,
                )
            )

            last_saved_frame = frame_number

        previous_frame = current_frame
        frame_number += 1

        if frame_number % 500 == 0:
            print(f"Processed {frame_number} frames...")

    return candidate_frames