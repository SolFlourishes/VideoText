"""
slide_debug.py

Utilities for displaying slide consolidation results.
"""

from models import Slide


def print_paragraphs(paragraphs) -> None:
    """
    Print a formatted list of reconstructed paragraphs.
    """

    if not paragraphs:
        print("<No Paragraphs>")
        return

    for i, paragraph in enumerate(paragraphs, start=1):

        print(f"[Paragraph {i}]")
        print(f"Type : {paragraph.text_type.name}")
        print(f"Text : {paragraph.text}")
        print(f"Lines: {len(paragraph.lines)}")

        for j, line in enumerate(paragraph.lines, start=1):
            print(
                f"   {j}. "
                f"({line.text_type.name}) "
                f"'{line.text}'"
            )

        print()


def print_slide_report(slides: list[Slide]) -> None:
    """
    Print a readable report of the consolidated slides.
    """

    print(f"\nCreated {len(slides)} slides.\n")

    for slide in slides:

        print("=" * 70)
        print(
            f"Slide {slide.slide_number} "
            f"({len(slide.builds)} build{'s' if len(slide.builds) != 1 else ''})"
        )
        print("=" * 70)

        for build_number, build in enumerate(slide.builds, start=1):

            frame = build.representative_frame

            start_time = build.candidate_frames[0].timestamp
            end_time = build.candidate_frames[-1].timestamp

            print(f"\nBuild {build_number}")
            print(
                f"Frames: {len(build.candidate_frames)} "
                f"({build.candidate_frames[0].frame_number}"
                f" - {build.candidate_frames[-1].frame_number})"
            )
            print(f"Duration: {start_time:.2f}s → {end_time:.2f}s")
            print(
                f"Representative Frame: {frame.frame_number}"
                f" | OCR Regions: {len(frame.ocr_results)}"
            )

            print("-" * 70)
            print("\nRaw OCR Results")

            for result in frame.ocr_results:
                print(
                    f"'{result.text}' "
                    f"({result.left:.0f}, {result.top:.0f})"
                )

            print("-" * 70)

            print_paragraphs(frame.text_paragraphs)

        #
        # Canonical slide after consolidating all builds.
        #
        print("-" * 70)
        print("\nCanonical Slide")
        print("-" * 70)

        print_paragraphs(slide.paragraphs)

        print()