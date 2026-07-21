"""
models.py

Data models used throughout the VideoText processing pipeline.
"""

from dataclasses import dataclass, field
import numpy as np


@dataclass
class OCRResult:
    """
    Represents a single OCR text region detected within a frame.
    """

    text: str
    confidence: float
    bounding_box: np.ndarray

    @property
    def left(self) -> float:
        """Left-most x coordinate."""
        return float(self.bounding_box[0])

    @property
    def top(self) -> float:
        """Top y coordinate."""
        return float(self.bounding_box[1])

    @property
    def right(self) -> float:
        """Right-most x coordinate."""
        return float(self.bounding_box[2])

    @property
    def bottom(self) -> float:
        """Bottom y coordinate."""
        return float(self.bounding_box[3])

    @property
    def center_x(self) -> float:
        """Horizontal center of the bounding box."""
        return (self.left + self.right) / 2

    @property
    def center_y(self) -> float:
        """Vertical center of the bounding box."""
        return (self.top + self.bottom) / 2


@dataclass
class CandidateFrame:
    """
    Represents a frame selected from the video for OCR processing.
    """

    frame_number: int
    timestamp: float
    image: np.ndarray
    difference_score: float

    ocr_results: list[OCRResult] = field(default_factory=list)

    is_duplicate: bool = False

    @property
    def combined_text(self) -> str:
        """
        Returns all detected OCR text combined into a single string.
        """
        return " ".join(
            result.text.strip()
            for result in self.ocr_results
            if result.text.strip()
        )