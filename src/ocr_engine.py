"""Engine-neutral OCR contract and the current PaddleOCR implementation."""

from typing import Any, Callable, Protocol, runtime_checkable

import numpy as np

from config import OCR_LANGUAGE
from models import OCRResult


@runtime_checkable
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
        """Initialize the Paddle model for the production singleton."""

        self._model()

    def recognize(self, image: Any) -> list[OCRResult]:
        """Invoke PaddleOCR and preserve its regions without normalization."""

        result = self._model().predict(image)
        parsed_results: list[OCRResult] = []

        if result:
            page = result[0]
            texts = page.get("rec_texts", [])
            scores = page.get("rec_scores", [])
            boxes = page.get("rec_boxes", [])
            if not (len(texts) == len(scores) == len(boxes)):
                raise ValueError(
                    "PaddleOCR returned inconsistent text, score, and box counts."
                )

            for text, score, box in zip(texts, scores, boxes):
                confidence = float(score)
                if not np.isfinite(confidence):
                    raise ValueError("PaddleOCR returned a non-finite confidence.")
                coordinates = np.asarray(box)
                if coordinates.shape != (4,):
                    raise ValueError(
                        "PaddleOCR returned a bounding box that is not "
                        "[left, top, right, bottom]."
                    )
                left, top, right, bottom = coordinates
                if left > right or top > bottom:
                    raise ValueError(
                        "PaddleOCR returned an invalid canonical bounding box."
                    )
                parsed_results.append(
                    OCRResult(
                        text=text,
                        confidence=confidence,
                        bounding_box=box,
                    )
                )

        return parsed_results


def discover_ocr_engines() -> dict[str, type[OCREngine]]:
    """Discover available adapter classes without creating OCR instances.

    Version 1.4 intentionally exposes only the built-in Paddle adapter. Future
    plugin sources can extend this discovery boundary without changing engine
    selection or production singleton behavior.
    """

    return {"paddle": PaddleOCREngine}


DEFAULT_OCR_ENGINE_NAME = "paddle"
# Copy discovery output so callers can never mutate the private registry.
_ENGINE_FACTORIES: dict[str, Callable[[], OCREngine]] = dict(
    discover_ocr_engines()
)


def get_registered_ocr_engines() -> tuple[str, ...]:
    """Return registered engine names in deterministic, immutable order."""

    return tuple(sorted(_ENGINE_FACTORIES))


def get_default_ocr_engine_name() -> str:
    """Return the stable name used by normal production OCR processing."""

    return DEFAULT_OCR_ENGINE_NAME


def create_ocr_engine(name: str) -> OCREngine:
    """Create an uninitialized OCR adapter for one registered engine name."""

    try:
        factory = _ENGINE_FACTORIES[name]
    except KeyError as error:
        available = ", ".join(get_registered_ocr_engines())
        raise ValueError(
            f"Unknown OCR engine: {name}. Available engines: {available}."
        ) from error
    return factory()


# Process-lifetime singleton retained for current model-loading performance.
_ocr_engine: PaddleOCREngine | None = None


def get_ocr_engine() -> PaddleOCREngine:
    """Return the lazily created, process-lifetime Paddle OCR adapter."""

    global _ocr_engine

    if _ocr_engine is None:
        _ocr_engine = create_ocr_engine(get_default_ocr_engine_name())
        assert isinstance(_ocr_engine, PaddleOCREngine)
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
