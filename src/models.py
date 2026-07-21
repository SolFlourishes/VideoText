"""
models.py

Data models used throughout the VideoText processing pipeline.
"""

from dataclasses import dataclass, field
from typing import List
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

from dataclasses import dataclass
from enum import Enum


class TextType(Enum):
    UNKNOWN = "unknown"
    TITLE = "title"
    BODY = "body"
    BULLET = "bullet"
    SUB_BULLET = "sub_bullet"
    NUMBERED = "numbered"
    FOOTER = "footer"


@dataclass
class TextLine:
    text: str

    top: float
    bottom: float
    left: float
    right: float

    confidence: float

    #
    # Structure Detection
    #
    text_type: TextType = TextType.UNKNOWN

    indent_level: int = 0

    bullet_level: int = 0

@dataclass
class TextParagraph:
    """
    A logical paragraph reconstructed from one or more visual text lines.
    """

    text: str

    lines: list[TextLine] = field(default_factory=list)

    text_type: TextType = TextType.UNKNOWN

    indent_level: int = 0

    bullet_level: int = 0

@dataclass
class ComparisonResult:
    """
    Describes the relationship between two candidate frames.
    """

    shared_lines: list[str] = field(default_factory=list)

    added_lines: list[str] = field(default_factory=list)

    removed_lines: list[str] = field(default_factory=list)

    similarity: float = 0.0

    decision: bool = False

    reason: str = ""

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

    #
    # Reconstructed visual lines
    #
    text_lines: list[TextLine] = field(default_factory=list)

    #
    # Reconstructed logical paragraphs
    #
    text_paragraphs: list[TextParagraph] = field(default_factory=list)

    is_duplicate: bool = False

    @property
    def combined_text(self) -> str:
        """
        Returns text optimized for comparison algorithms.
        """

        if self.text_lines:
            return " ".join(
                line.text.strip()
                for line in self.text_lines
                if line.text.strip()
            )

        return " ".join(
            result.text.strip()
            for result in self.ocr_results
            if result.text.strip()
        )

    @property
    def formatted_text(self) -> str:
        """
        Returns readable text preserving line breaks.
        """

        if self.text_lines:
            return "\n".join(
                line.text.strip()
                for line in self.text_lines
                if line.text.strip()
            )

        return "\n".join(
            result.text.strip()
            for result in self.ocr_results
            if result.text.strip()
        )


@dataclass
class SlideBuild:
    """
    Represents one unique build state of a slide.

    Multiple sampled frames may correspond to this build.
    """

    candidate_frames: list[CandidateFrame] = field(default_factory=list)

    final_text: str = ""

    @property
    def representative_frame(self) -> CandidateFrame:
        """
        Return the first frame for reporting/export.
        """
        return self.candidate_frames[0]


@dataclass
class Slide:
    """
    Represents one logical slide presented during the lecture.

    A slide may contain multiple builds as bullets or graphics are
    progressively revealed.
    """

    slide_number: int
    start_time: float
    end_time: float

    builds: List[SlideBuild] = field(default_factory=list)

    final_text: str = ""