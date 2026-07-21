"""
main.py

Application entry point for VideoText.
"""

from reading_order import reconstruct_reading_order
from slide_consolidator import consolidate_slides

from video_reader import open_video
from frame_analyzer import analyze_video
from frame_saver import save_candidate_frames
from ocr_engine import perform_ocr

from config import (
    CANDIDATE_FRAME_FOLDER,
    CANDIDATE_CACHE,
    OCR_CACHE,
    READING_ORDER_CACHE,
)

from cache_manager import (
    save_cache,
    load_cache,
)

from menu import select_start_stage


def main():
    """
    Main application entry point.
    """

    start_stage = select_start_stage()

    video = None

    #
    # ----------------------------
    # Stage 1 - Video Analysis
    # ----------------------------
    #
    if start_stage == "video":

        video_path = input("Video: ")

        video, fps = open_video(video_path)

        print("Video opened successfully!")

        candidate_frames = analyze_video(video, fps)

        save_candidate_frames(
            candidate_frames,
            CANDIDATE_FRAME_FOLDER,
        )

        save_cache(
            candidate_frames,
            CANDIDATE_CACHE,
        )

    #
    # ----------------------------
    # Stage 2 - OCR
    # ----------------------------
    #
    elif start_stage == "ocr":

        print("Loading cached candidate frames...")

        candidate_frames = load_cache(
            CANDIDATE_CACHE,
        )

    #
    # ----------------------------
    # Stage 3 - Reading Order
    # ----------------------------
    #
    elif start_stage == "reading_order":

        print("Loading cached OCR results...")

        candidate_frames = load_cache(
            OCR_CACHE,
        )

    #
    # ----------------------------
    # Stage 4 - Slide Consolidation
    # ----------------------------
    #
    elif start_stage == "slide_consolidation":

        print("Loading cached reading order...")

        candidate_frames = load_cache(
            READING_ORDER_CACHE,
        )

        slides = consolidate_slides(candidate_frames)

        print(f"\nCreated {len(slides)} slides.")

        return

    else:

        print(f"Stage '{start_stage}' is not implemented yet.")
        return

    #
    # OCR
    #
    if start_stage != "reading_order":

        candidate_frames = perform_ocr(candidate_frames)

        save_cache(
            candidate_frames,
            OCR_CACHE,
        )

    #
    # Reading Order
    #
    candidate_frames = reconstruct_reading_order(
        candidate_frames,
    )

    save_cache(
        candidate_frames,
        READING_ORDER_CACHE,
    )

    #
    # Release video.
    #
    if video is not None:
        video.release()

    print("\nProcessing complete.")

    #
    # Summary
    #
    print(f"\nSelected {len(candidate_frames)} candidate frames.")

    values = [frame.difference_score for frame in candidate_frames]

    print(f"Minimum Difference : {min(values):.2f}")
    print(f"Maximum Difference : {max(values):.2f}")
    print(f"Average Difference : {sum(values) / len(values):.2f}")

    print("\nTop 10 Largest Changes")

    top_changes = sorted(
        candidate_frames,
        key=lambda frame: frame.difference_score,
        reverse=True,
    )[:10]

    for frame in top_changes:
        print(
            f"Frame {frame.frame_number:5d}: "
            f"{frame.difference_score:.2f}"
        )


if __name__ == "__main__":
    main()