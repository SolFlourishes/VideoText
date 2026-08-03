"""Deterministic descriptive statistics for preserved raw OCR evidence."""

from dataclasses import dataclass
from statistics import median
from typing import Sequence

from config import MIN_CONFIDENCE
from models import CandidateFrame


@dataclass(frozen=True)
class OCRConfidenceStats:
    """Confidence summary calculated from one frame's raw OCR regions."""

    region_count: int
    minimum: float | None
    maximum: float | None
    mean: float | None
    median: float | None
    below_threshold_count: int
    below_threshold_proportion: float
    threshold: float


@dataclass(frozen=True)
class DocumentOCRConfidenceStats:
    """Confidence summary calculated from all raw OCR regions in a document."""

    frame_count: int
    frames_with_ocr: int
    region_count: int
    minimum: float | None
    maximum: float | None
    mean: float | None
    median: float | None
    below_threshold_count: int
    below_threshold_proportion: float
    threshold: float


def calculate_ocr_confidence_stats(frame: CandidateFrame) -> OCRConfidenceStats:
    """Describe preserved raw OCR confidence without changing frame evidence."""

    confidences = [result.confidence for result in frame.raw_ocr_results]
    region_count = len(confidences)
    below_threshold_count = sum(
        confidence < MIN_CONFIDENCE
        for confidence in confidences
    )

    if not confidences:
        return OCRConfidenceStats(
            region_count=0,
            minimum=None,
            maximum=None,
            mean=None,
            median=None,
            below_threshold_count=0,
            below_threshold_proportion=0.0,
            threshold=MIN_CONFIDENCE,
        )

    return OCRConfidenceStats(
        region_count=region_count,
        minimum=min(confidences),
        maximum=max(confidences),
        mean=sum(confidences) / region_count,
        median=median(confidences),
        below_threshold_count=below_threshold_count,
        below_threshold_proportion=below_threshold_count / region_count,
        threshold=MIN_CONFIDENCE,
    )


def calculate_document_ocr_confidence_stats(
    frames: Sequence[CandidateFrame],
) -> DocumentOCRConfidenceStats:
    """Describe all preserved raw OCR evidence across a document's frames."""

    frame_count = len(frames)
    frames_with_ocr = sum(bool(frame.raw_ocr_results) for frame in frames)
    confidences = [
        result.confidence
        for frame in frames
        for result in frame.raw_ocr_results
    ]
    region_count = len(confidences)
    below_threshold_count = sum(
        confidence < MIN_CONFIDENCE
        for confidence in confidences
    )

    if not confidences:
        return DocumentOCRConfidenceStats(
            frame_count=frame_count,
            frames_with_ocr=0,
            region_count=0,
            minimum=None,
            maximum=None,
            mean=None,
            median=None,
            below_threshold_count=0,
            below_threshold_proportion=0.0,
            threshold=MIN_CONFIDENCE,
        )

    return DocumentOCRConfidenceStats(
        frame_count=frame_count,
        frames_with_ocr=frames_with_ocr,
        region_count=region_count,
        minimum=min(confidences),
        maximum=max(confidences),
        mean=sum(confidences) / region_count,
        median=median(confidences),
        below_threshold_count=below_threshold_count,
        below_threshold_proportion=below_threshold_count / region_count,
        threshold=MIN_CONFIDENCE,
    )
