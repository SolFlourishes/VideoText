"""
frame_analyzer.py

Analyzes a video and identifies candidate frames for OCR.
"""

from time import monotonic

import numpy as np

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
PROGRESS_FRAME_INTERVAL = 500
PROGRESS_TIME_INTERVAL_SECONDS = 1.0


def _is_visible_slide(frame):
    """Return whether *frame* contains visible slide content, not a black end frame."""
    return np.max(frame) > 0


def _save_candidate(
    candidate_frames,
    frame,
    frame_number,
    timestamp,
    difference_score,
    allow_black=False,
):
    """Save a visible, non-duplicate candidate and report whether it was saved."""
    if not allow_black and not _is_visible_slide(frame):
        return False

    if candidate_frames and np.array_equal(candidate_frames[-1].image, frame):
        return False

    candidate_frames.append(
        CandidateFrame(
            frame_number=frame_number,
            timestamp=timestamp,
            image=frame.copy(),
            difference_score=difference_score,
        )
    )
    return True


def _commit_pending_frame(
    candidate_frames,
    pending_frame,
    pending_frame_number,
    pending_timestamp,
    pending_score,
    stable_count,
):
    """Commit an eligible pending transition through the shared save rule."""
    if pending_frame is None or stable_count < STABLE_FRAMES_REQUIRED:
        return False

    return _save_candidate(
        candidate_frames,
        pending_frame,
        pending_frame_number,
        pending_timestamp,
        pending_score,
    )


def _terminal_frame_is_stable(stability_window):
    """Confirm that the terminal quiet window did not cumulatively fade or drift."""
    if len(stability_window) < STABLE_FRAMES_REQUIRED + 1:
        return False

    first_frame = stability_window[0][1]
    last_frame = stability_window[-1][1]
    return (
        calculate_frame_difference(first_frame, last_frame)
        < FRAME_DIFFERENCE_THRESHOLD
    )


def analyze_video(
    video,
    fps,
    progress_callback=None,
    total_frames=None,
    clock=monotonic,
):
    """
    Analyze every frame in a video.

    Args:
        video: OpenCV VideoCapture object.
        fps: Frames per second.
        progress_callback: Optional callback receiving processed and total frames.
        total_frames: Optional reliable total supplied by the video reader.
        clock: Monotonic clock used only to throttle progress updates.

    Returns:
        List[CandidateFrame]
    """

    candidate_frames = []

    success, previous_frame = video.read()

    if not success:
        return candidate_frames

    _save_candidate(
        candidate_frames,
        previous_frame,
        frame_number=0,
        timestamp=0.0,
        difference_score=0.0,
        allow_black=True,
    )

    frame_number = 1
    last_saved_frame = 0
    last_progress_frame = 1
    last_progress_time = clock()

    if progress_callback is not None:
        progress_callback(1, total_frames)

    # Tracks an active transition.
    transition_active = False
    stable_count = 0

    pending_frame = None
    pending_frame_number = 0
    pending_timestamp = 0.0
    pending_score = 0.0

    # Keeps the same quiet-frame evidence used for transitions. At EOF it
    # confirms a short final slide without treating a fade as a stable slide.
    stability_window = [(0, previous_frame.copy())]

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

        if score < FRAME_DIFFERENCE_THRESHOLD:
            stability_window.append((frame_number, current_frame.copy()))
            if len(stability_window) > STABLE_FRAMES_REQUIRED + 1:
                stability_window.pop(0)
        else:
            stability_window = [(frame_number, current_frame.copy())]

        # Transition detected.
        if score >= FRAME_DIFFERENCE_THRESHOLD:
            transition_active = True
            stable_count = 0

            pending_frame = current_frame.copy()
            pending_frame_number = frame_number
            pending_timestamp = frame_number / fps
            pending_score = score

        # Wait until the image has stabilized.
        elif transition_active:
            stable_count += 1

            if stable_count >= STABLE_FRAMES_REQUIRED:
                if _commit_pending_frame(
                    candidate_frames,
                    pending_frame,
                    pending_frame_number,
                    pending_timestamp,
                    pending_score,
                    stable_count,
                ):
                    last_saved_frame = pending_frame_number

                transition_active = False
                stable_count = 0

        # Long static periods.
        elif (
            seconds_since_last_save
            >= MAX_SECONDS_BETWEEN_CAPTURES
        ):
            if _save_candidate(
                candidate_frames,
                current_frame,
                frame_number,
                frame_number / fps,
                score,
            ):
                last_saved_frame = frame_number

        previous_frame = current_frame
        frame_number += 1

        if progress_callback is not None:
            now = clock()
            if (
                frame_number - last_progress_frame >= PROGRESS_FRAME_INTERVAL
                or now - last_progress_time >= PROGRESS_TIME_INTERVAL_SECONDS
            ):
                progress_callback(frame_number, total_frames)
                last_progress_frame = frame_number
                last_progress_time = now

    # A final slide can be stable for fewer seconds than the normal static
    # timeout. Capture it only when the existing quiet-frame requirement is
    # met, the whole window is stable, and no transition remains unresolved.
    if not transition_active and _terminal_frame_is_stable(stability_window):
        terminal_frame_number, terminal_frame = stability_window[-1]
        _save_candidate(
            candidate_frames,
            terminal_frame,
            terminal_frame_number,
            terminal_frame_number / fps,
            calculate_frame_difference(candidate_frames[-1].image, terminal_frame)
            if candidate_frames
            else 0.0,
        )

    # EOF can arrive after a final transition has become stable but before a
    # later frame exercises the ordinary commit path.
    _commit_pending_frame(
        candidate_frames,
        pending_frame,
        pending_frame_number,
        pending_timestamp,
        pending_score,
        stable_count,
    )

    if progress_callback is not None:
        progress_callback(frame_number, total_frames)

    return candidate_frames
