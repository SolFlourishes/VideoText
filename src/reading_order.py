from models import CandidateFrame


MIN_CONFIDENCE = 0.60


def reconstruct_reading_order(
    candidate_frames: list[CandidateFrame],
) -> list[CandidateFrame]:
    """
    Filters low-confidence OCR results and sorts the remaining text
    into an approximate reading order (top-to-bottom, left-to-right).
    """

    for frame in candidate_frames:

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

    return candidate_frames