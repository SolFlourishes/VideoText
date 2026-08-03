"""Engine-neutral OCR contract and the current PaddleOCR implementation."""

from typing import Any, Protocol

from config import OCR_LANGUAGE
from models import OCRResult


class OCREngine(Protocol):
    """Recognize text regions in one image using canonical OCR results."""

    def recognize(self, image: Any) -> list[OCRResult]:
        """Return recognized regions in the engine's original response order."""


def _load_paddle_ocr_class():
    """Import PaddleOCR only when the Paddle adapter first needs its model."""

    from paddleocr import PaddleOCR

    return PaddleOCR


class PaddleOCREngine:
    """Adapt PaddleOCR predictions to VideoText's canonical OCRResult model."""

    def __init__(self) -> None:
        self._paddle_ocr = None

    def _model(self):
        """Create and retain the Paddle model only on first recognition use."""

        if self._paddle_ocr is None:
            print("\nLoading PaddleOCR model...\n")
            paddle_ocr_class = _load_paddle_ocr_class()
            self._paddle_ocr = paddle_ocr_class(
                use_textline_orientation=True,
                lang=OCR_LANGUAGE,
            )
            print("PaddleOCR model loaded successfully.\n")
        return self._paddle_ocr

    def initialize(self) -> None:
        """Initialize the Paddle model while preserving factory compatibility."""

        self._model()

    def predict(self, image: Any):
        """Return Paddle's unparsed response for temporary legacy callers."""

        return self._model().predict(image)

    def recognize(self, image: Any) -> list[OCRResult]:
        """Invoke PaddleOCR and preserve its regions without normalization."""

        result = self.predict(image)
        parsed_results: list[OCRResult] = []

        if result:
            page = result[0]
            texts = page.get("rec_texts", [])
            scores = page.get("rec_scores", [])
            boxes = page.get("rec_boxes", [])

            for text, score, box in zip(texts, scores, boxes):
                parsed_results.append(
                    OCRResult(
                        text=text,
                        confidence=float(score),
                        bounding_box=box,
                    )
                )

        return parsed_results


# Process-lifetime singleton retained for current model-loading performance.
_ocr_engine: PaddleOCREngine | None = None


def get_ocr_engine() -> PaddleOCREngine:
    """Return the lazily created, process-lifetime Paddle OCR adapter."""

    global _ocr_engine

    if _ocr_engine is None:
        _ocr_engine = PaddleOCREngine()
        # Preserve existing behavior: the first factory call loads the model
        # before the caller begins its frame-processing console output.
        _ocr_engine.initialize()

    return _ocr_engine


def perform_ocr(candidate_frames, progress_callback=None):
    """Populate candidate frames through the engine-neutral recognition contract."""

    ocr: OCREngine = get_ocr_engine()

    print("Running OCR...\n")

    for index, frame in enumerate(candidate_frames, start=1):
        print(
            f"[{index}/{len(candidate_frames)}] "
            f"Frame {frame.frame_number}"
        )

        # Keep separate containers around the same canonical region objects.
        # Reading order may later replace only the working collection.
        parsed_results = ocr.recognize(frame.image)
        frame.raw_ocr_results = list(parsed_results)
        frame.ocr_results = list(parsed_results)

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

        if progress_callback is not None:
            progress_callback(index, len(candidate_frames))

    print("\nOCR Complete.\n")

    return candidate_frames
