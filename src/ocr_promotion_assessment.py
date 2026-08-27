"""Derived, language-neutral observations for future OCR text promotion.

This module does not mutate OCR evidence or decide which text enters a
Presentation.  It supplies immutable observations and assessments that a
later promotion step can consume.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import re
import unicodedata

from config import MIN_CONFIDENCE


class UnicodeScript(str, Enum):
    """Writing-system categories observable in recognized Unicode text."""

    LATIN = "Latin"
    HEBREW = "Hebrew"
    ARABIC = "Arabic"
    CYRILLIC = "Cyrillic"
    HANGUL = "Hangul"
    HAN = "Han"
    OTHER_UNKNOWN = "Other/Unknown"


class OCRPromotionDisposition(str, Enum):
    """Possible outcomes for a future OCR-to-Presentation promotion step."""

    PROMOTED = "Promoted"
    PROMOTED_REVIEW_RECOMMENDED = "Promoted / Review Recommended"
    NOT_PROMOTED_LOW_OCR_EVIDENCE = "Not Promoted / Low OCR Evidence"
    NOT_PROMOTED_FRAGMENT = "Not Promoted / Fragment"


class OCRPromotionReason(str, Enum):
    """Observable reasons associated with a promotion assessment."""

    SCRIPT_MISMATCH = "Script Mismatch"
    FRAGMENT_LIKE_STRUCTURE = "Fragment-like Structure"
    WEAK_OCR_EVIDENCE = "Weak OCR Evidence"
    TINY_VISUAL_FOOTPRINT = "Tiny Visual Footprint"
    UNCORROBORATED_OBSERVATION = "Uncorroborated Observation"


@dataclass(frozen=True)
class OCRRecognitionProfile:
    """Scripts an OCR recognition configuration is expected to handle."""

    name: str
    recognized_scripts: frozenset[UnicodeScript]


CURRENT_OCR_RECOGNITION_PROFILE = OCRRecognitionProfile(
    name="PaddleOCR English recognition",
    recognized_scripts=frozenset({UnicodeScript.LATIN}),
)


@dataclass(frozen=True)
class OCRPromotionAssessment:
    """Immutable derived assessment; never a calibrated confidence score."""

    disposition: OCRPromotionDisposition
    reasons: tuple[OCRPromotionReason, ...]
    observed_scripts: tuple[UnicodeScript, ...]
    protected_short_content: bool


@dataclass(frozen=True)
class OCRPromotionContext:
    """Small derived context for one reconstructed text observation.

    ``confidence`` is the existing OCR region/line value, not a combined or
    calibrated score.  Bounding boxes use ``left, top, right, bottom`` and
    frame dimensions use ``width, height``.
    """

    confidence: float | None = None
    region_count: int | None = None
    bounding_box: tuple[float, float, float, float] | None = None
    frame_dimensions: tuple[int, int] | None = None
    observation_count: int = 1

    def __post_init__(self) -> None:
        if self.confidence is not None and not 0 <= self.confidence <= 1:
            raise ValueError("OCR confidence must be between 0 and 1.")
        if self.region_count is not None and self.region_count < 1:
            raise ValueError("OCR region count must be at least one.")
        if self.observation_count < 1:
            raise ValueError("Observation count must be at least one.")
        if self.bounding_box is not None:
            left, top, right, bottom = self.bounding_box
            if right < left or bottom < top:
                raise ValueError("OCR bounding box must use canonical coordinates.")
        if self.frame_dimensions is not None:
            width, height = self.frame_dimensions
            if width <= 0 or height <= 0:
                raise ValueError("Frame dimensions must be positive.")


@dataclass(frozen=True)
class OCRPromotionRecord:
    """Audit record for one canonical paragraph promotion decision."""

    text: str
    assessment: OCRPromotionAssessment
    context: OCRPromotionContext
    source_frame_number: int | None
    included_in_presentation: bool


_SCRIPT_ORDER = {script: index for index, script in enumerate(UnicodeScript)}
_COMPACT_VALUE = re.compile(r"^\S(?:.{0,14}\S)?$")
_SINGLE_UPPER_TOKEN = re.compile(r"^[^\W\d_]{2,5}$", re.UNICODE)

# Reading-order processing already rejects values below MIN_CONFIDENCE.  The
# next ten percentage points are treated only as weak supporting evidence.
NEAR_CONFIDENCE_MARGIN = 0.10

# A box occupying no more than 0.1% of the frame is visually tiny.  Relative
# area avoids resolution-specific pixel thresholds and is never sufficient by
# itself to withhold text.
TINY_FRAME_AREA_PROPORTION = 0.001


def _script_for_character(character: str) -> UnicodeScript | None:
    """Return a script for a letter, ignoring Common/neutral characters."""

    if not character.isalpha():
        return None

    name = unicodedata.name(character, "")
    if name.startswith("LATIN"):
        return UnicodeScript.LATIN
    if name.startswith("HEBREW"):
        return UnicodeScript.HEBREW
    if name.startswith("ARABIC"):
        return UnicodeScript.ARABIC
    if name.startswith("CYRILLIC"):
        return UnicodeScript.CYRILLIC
    if name.startswith("HANGUL"):
        return UnicodeScript.HANGUL
    if name.startswith(("CJK UNIFIED IDEOGRAPH", "CJK COMPATIBILITY IDEOGRAPH")):
        return UnicodeScript.HAN
    return UnicodeScript.OTHER_UNKNOWN


def observe_scripts(text: str) -> frozenset[UnicodeScript]:
    """Observe Unicode scripts in recognized text without inferring language."""

    return frozenset(
        script
        for character in text
        if (script := _script_for_character(character)) is not None
    )


def is_protected_short_content(text: str) -> bool:
    """Identify compact content that short-fragment rules must not discard.

    This deliberately recognizes shapes, not words or languages.  Context may
    later distinguish a legitimate one-letter variable from a weak OCR
    fragment; shortness alone cannot do so safely.
    """

    value = text.strip()
    if not value or not _COMPACT_VALUE.fullmatch(value):
        return False

    if any(character.isdigit() for character in value):
        return True
    # A lowercase single character is a common language-neutral variable
    # shape. Uppercase one-letter observations need context because the real
    # weak-fragment corpus includes isolated "V" and "M" results.
    if len(value) == 1 and value.isalpha() and value.islower():
        return True
    return bool(
        _SINGLE_UPPER_TOKEN.fullmatch(value)
        and value.upper() == value
    )


def assess_ocr_text(
    text: str,
    recognition_profile: OCRRecognitionProfile = CURRENT_OCR_RECOGNITION_PROFILE,
) -> OCRPromotionAssessment:
    """Create a conservative script-aware assessment of recognized OCR text.

    Script mismatch recommends review but never withholds text.  Fragment and
    low-evidence dispositions are defined for the later promotion task and are
    not produced here.
    """

    observed = observe_scripts(text)
    mismatched = observed - recognition_profile.recognized_scripts
    reasons = (
        (OCRPromotionReason.SCRIPT_MISMATCH,)
        if mismatched
        else ()
    )
    disposition = (
        OCRPromotionDisposition.PROMOTED_REVIEW_RECOMMENDED
        if reasons
        else OCRPromotionDisposition.PROMOTED
    )
    return OCRPromotionAssessment(
        disposition=disposition,
        reasons=reasons,
        observed_scripts=tuple(sorted(observed, key=_SCRIPT_ORDER.__getitem__)),
        protected_short_content=is_protected_short_content(text),
    )


def _is_fragment_like(text: str) -> bool:
    tokens = text.split()
    alphabetic_tokens = [token for token in tokens if token.isalpha()]
    if not alphabetic_tokens or len(alphabetic_tokens) != len(tokens):
        return False
    if len(alphabetic_tokens) == 1:
        return len(alphabetic_tokens[0]) == 1
    isolated = sum(len(token) == 1 for token in alphabetic_tokens)
    return isolated / len(alphabetic_tokens) >= 0.5


def _has_tiny_footprint(context: OCRPromotionContext) -> bool:
    if context.bounding_box is None or context.frame_dimensions is None:
        return False
    left, top, right, bottom = context.bounding_box
    frame_width, frame_height = context.frame_dimensions
    area = max(0.0, right - left) * max(0.0, bottom - top)
    return area / (frame_width * frame_height) <= TINY_FRAME_AREA_PROPORTION


def assess_ocr_promotion(
    text: str,
    context: OCRPromotionContext,
    recognition_profile: OCRRecognitionProfile = CURRENT_OCR_RECOGNITION_PROFILE,
) -> OCRPromotionAssessment:
    """Assess contextual weak-fragment evidence without changing output.

    Fragment non-promotion requires fragment-like structure, near-threshold
    OCR evidence, and either a tiny footprint or an uncorroborated observation.
    Protected compact content and out-of-profile scripts are preserved.
    """

    foundational = assess_ocr_text(text, recognition_profile)
    observed = frozenset(foundational.observed_scripts)
    script_mismatch = bool(observed - recognition_profile.recognized_scripts)
    fragment_like = _is_fragment_like(text)
    weak_evidence = (
        context.confidence is not None
        and context.confidence <= MIN_CONFIDENCE + NEAR_CONFIDENCE_MARGIN
    )
    tiny_footprint = _has_tiny_footprint(context)
    uncorroborated = context.observation_count == 1

    supporting_context = tiny_footprint or uncorroborated
    suppress_fragment = (
        fragment_like
        and weak_evidence
        and supporting_context
        and not foundational.protected_short_content
        and not script_mismatch
    )

    reasons = list(foundational.reasons)
    if fragment_like:
        reasons.append(OCRPromotionReason.FRAGMENT_LIKE_STRUCTURE)
    if weak_evidence:
        reasons.append(OCRPromotionReason.WEAK_OCR_EVIDENCE)
    if tiny_footprint:
        reasons.append(OCRPromotionReason.TINY_VISUAL_FOOTPRINT)
    if suppress_fragment and uncorroborated:
        reasons.append(OCRPromotionReason.UNCORROBORATED_OBSERVATION)

    if suppress_fragment:
        disposition = OCRPromotionDisposition.NOT_PROMOTED_FRAGMENT
    elif foundational.reasons or weak_evidence:
        disposition = OCRPromotionDisposition.PROMOTED_REVIEW_RECOMMENDED
    else:
        disposition = OCRPromotionDisposition.PROMOTED

    return OCRPromotionAssessment(
        disposition=disposition,
        reasons=tuple(reasons),
        observed_scripts=foundational.observed_scripts,
        protected_short_content=foundational.protected_short_content,
    )
