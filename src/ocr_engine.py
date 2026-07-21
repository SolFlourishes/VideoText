"""
ocr_engine.py

Runs OCR on candidate frames using PaddleOCR.
"""

from paddleocr import PaddleOCR

from config import OCR_LANGUAGE
from models import OCRResult

# Singleton OCR engine
_ocr_engine = None


def get_ocr_engine():
    """
    Create the OCR engine on first use.

    Returns:
        PaddleOCR
    """
    global _ocr_engine

    if _ocr_engine is None:

        print("\nLoading PaddleOCR model...\n")

        _ocr_engine = PaddleOCR(
            use_textline_orientation=True,
            lang=OCR_LANGUAGE,
        )

        print("PaddleOCR model loaded successfully.\n")

    return _ocr_engine


def perform_ocr(candidate_frames):
    """
    Perform OCR on all candidate frames.

    Args:
        candidate_frames: List[CandidateFrame]

    Returns:
        The same list of CandidateFrame objects populated with OCR results.
    """

    ocr = get_ocr_engine()

    print("Running OCR...\n")

    for index, frame in enumerate(candidate_frames, start=1):

        print(
            f"[{index}/{len(candidate_frames)}] "
            f"Frame {frame.frame_number}"
        )

        # Run OCR
        result = ocr.predict(frame.image)

        # Clear any previous OCR results
        frame.ocr_results.clear()

        if result:

            page = result[0]

            texts = page.get("rec_texts", [])
            scores = page.get("rec_scores", [])
            boxes = page.get("rec_boxes", [])

            for text, score, box in zip(texts, scores, boxes):
                
                frame.ocr_results.append(
                    OCRResult(
                        text=text,
                        confidence=float(score),
                        bounding_box=box,
                    )
                )
                                

        print(f"    Found {len(frame.ocr_results)} text regions.")

        if frame.ocr_results:

            for number, ocr_result in enumerate(frame.ocr_results, start=1):

                print(
                    f"      {number}. "
                    f"{ocr_result.text} "
                    f"({ocr_result.confidence:.2%})"
                )

            print(f"      Combined: {frame.combined_text}")

        print()

    print("\nOCR Complete.\n")

    return candidate_frames