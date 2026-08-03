from models import CandidateFrame, ensure_raw_ocr_results
from config import MIN_CONFIDENCE
from text_reconstruction import reconstruct_lines_with_metadata
from structure_detection import detect_structure
from paragraph_reconstruction import reconstruct_paragraphs


def reconstruct_reading_order(
    candidate_frames: list[CandidateFrame],
    progress_callback=None,
) -> list[CandidateFrame]:
    """
    Filters low-confidence OCR results and sorts the remaining text
    into an approximate reading order (top-to-bottom, left-to-right).
    """

    for index, frame in enumerate(candidate_frames, start=1):

        # Legacy checkpoints may lack raw evidence.  Normalize it before the
        # working list is replaced by confidence-filtered OCR results.
        ensure_raw_ocr_results(frame)

        # Remove low-confidence detections
        filtered_results = [
            result
            for result in frame.ocr_results
            if result.confidence >= MIN_CONFIDENCE
        ]

        # Sort by reading order
        filtered_results.sort(
            key=lambda result: (
                result.top,
                result.left,
            )
        )

        frame.ocr_results = filtered_results
        frame.text_lines, frame.line_reconstruction_metadata = reconstruct_lines_with_metadata(filtered_results)

        detect_structure(frame)

        #
        # Temporary Debug
        #
        print(f"\nFrame {frame.frame_number}")
        min_left = min(line.left for line in frame.text_lines) if frame.text_lines else 0

        for line in frame.text_lines:
            print(
                f"{line.text_type.name:10} "
                f"Left={line.left:4} "
                f"Indent={line.left - min_left:4} "
                f"'{line.text}'"
            )

        reconstruct_paragraphs(frame)

        if progress_callback is not None:
            progress_callback(index, len(candidate_frames))

    return candidate_frames
