"""Unregistered RapidOCR adapter retained for Version 1.5 feasibility work.

This module is deliberately not imported by production OCR registration. Paddle
remains VideoText's sole registered and default engine until evaluation results
justify a separate integration task.
"""

from typing import Any

import numpy as np

from models import OCRResult


def _load_rapid_ocr_class():
    """Import RapidOCR only if this evaluation adapter is used."""

    from rapidocr import RapidOCR

    return RapidOCR


def _rectangle_from_quad(box: Any) -> np.ndarray:
    """Convert one documented RapidOCR quadrilateral to VideoText geometry.

    RapidOCR returns four ``(x, y)`` points per text line. VideoText's existing
    canonical model represents an axis-aligned region as ``left, top, right,
    bottom``. The enclosing rectangle preserves the full region extent without
    changing the OCR engine's text, score, or region order.
    """

    points = np.asarray(box)
    if points.shape != (4, 2):
        raise ValueError(
            "RapidOCR returned a bounding box that is not a four-point "
            f"quadrilateral: shape {points.shape!r}."
        )
    return np.array((
        points[:, 0].min(),
        points[:, 1].min(),
        points[:, 0].max(),
        points[:, 1].max(),
    ))


class RapidOCREngine:
    """Map documented RapidOCR line results to canonical ``OCRResult`` objects.

    The adapter initializes RapidOCR lazily and is intentionally unregistered.
    It is available only for controlled Version 1.5 adapter validation.
    """

    def __init__(self) -> None:
        self._rapid_ocr = None

    def _model(self):
        """Create and retain one RapidOCR instance when first used."""

        if self._rapid_ocr is None:
            self._rapid_ocr = _load_rapid_ocr_class()()
        return self._rapid_ocr

    def initialize(self) -> None:
        """Initialize the evaluation adapter without recognizing a frame."""

        self._model()

    def recognize(self, image: Any) -> list[OCRResult]:
        """Recognize one image without changing RapidOCR result ordering."""

        output = self._model()(image)
        if output is None:
            return []

        boxes = output.boxes
        texts = output.txts
        scores = output.scores
        if not (len(boxes) == len(texts) == len(scores)):
            raise ValueError(
                "RapidOCR returned inconsistent box, text, and score counts."
            )

        return [
            OCRResult(
                text=text,
                confidence=_confidence(score),
                bounding_box=_rectangle_from_quad(box),
            )
            for box, text, score in zip(boxes, texts, scores)
        ]


def _confidence(score: Any) -> float:
    """Return one raw RapidOCR confidence or reject a non-finite value."""

    confidence = float(score)
    if not np.isfinite(confidence):
        raise ValueError("RapidOCR returned a non-finite confidence.")
    return confidence
