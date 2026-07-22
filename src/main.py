"""
main.py

Application entry point for VideoText.
"""

from reading_order import reconstruct_reading_order
from slide_consolidator import consolidate_slides
from slide_debug import print_slide_report
from markdown_exporter import export_markdown
from models import Presentation

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


def print_summary(candidate_frames):
    """
    Print processing summary.
    """

    print("\nProcessing complete.")

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

    elif start_stage == "ocr":

        print("Loading cached candidate frames...")

        candidate_frames = load_cache(
            CANDIDATE_CACHE,
        )

    elif start_stage == "reading_order":

        print("Loading cached OCR results...")

        candidate_frames = load_cache(
            OCR_CACHE,
        )

    elif start_stage == "slide_consolidation":

        print("Loading cached reading order...")

        candidate_frames = load_cache(
            READING_ORDER_CACHE,
        )

    elif start_stage == "export":

        print("Export is not implemented yet.")
        return

    else:

        print(f"Unknown stage: {start_stage}")
        return

    #
    # ----------------------------
    # OCR
    # ----------------------------
    #
    if start_stage in ("video", "ocr"):

        print("\n=== OCR ===")

        candidate_frames = perform_ocr(candidate_frames)

        save_cache(
            candidate_frames,
            OCR_CACHE,
        )

    #
    # ----------------------------
    # Reading Order
    # ----------------------------
    #
    if start_stage in ("video", "ocr", "reading_order"):

        print("\n=== Reading Order ===")

        candidate_frames = reconstruct_reading_order(
            candidate_frames,
        )

        save_cache(
            candidate_frames,
            READING_ORDER_CACHE,
        )

    #
    # ----------------------------
    # Slide Consolidation
    # ----------------------------
    #
    print("\n=== Slide Consolidation ===")

    slides = consolidate_slides(candidate_frames)

    presentation = Presentation(
        metadata={
            "start_stage": start_stage,
        },
        slides=slides,
        statistics={
            "candidate_frames": len(candidate_frames),
            "slides_detected": len(slides),
        },
    )

    print_slide_report(slides)

    #
    # ----------------------------
    # Markdown Export
    # ----------------------------
    #
    output_path = "output/videotext_export.md"

    saved_path = export_markdown(
        presentation,
        output_path,
    )

    print("\n=== Export ===")
    print("Export complete.")
    print(f"Saved to: {saved_path}")

    #
    # Cleanup
    #
    if video is not None:
        video.release()

    print_summary(candidate_frames)

    return presentation


if __name__ == "__main__":
    main()
