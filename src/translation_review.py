"""Deterministic, provider-neutral review prioritization for translations.

This module evaluates evidence already present in immutable translation results.
It never calls a provider, rewrites translation text, or claims correctness.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from enum import Enum
import re
from types import MappingProxyType
from typing import Any, Iterable, Mapping

from translation_contract import TranslationResult, TranslationStatus


ASSESSMENT_REVISION = "translation-review-v1"
SOURCE_COPY_MINIMUM_WORDS = 4
SOURCE_COPY_MINIMUM_CHARACTERS = 20
SOURCE_COPY_SIMILARITY_THRESHOLD = 0.96
STRUCTURE_LOSS_MINIMUM_LINES = 3

_NUMBER_TOKEN = re.compile(r"(?<![\w.])\d+(?:[.,]\d+)?")
_WORD_TOKEN = re.compile(r"[^\W\d_]+", re.UNICODE)
_URL = re.compile(r"(?:https?://|www\.)", re.IGNORECASE)
_BULLET_LINE = re.compile(r"^\s*(?:[-*•◦]|\d+[.)])\s+")


class TranslationReviewStatus(Enum):
    """Human-review priority, never a translation correctness claim."""

    NORMAL_REVIEW = "normal_review"
    REVIEW_RECOMMENDED = "review_recommended"
    TRANSLATION_FAILED = "translation_failed"


class HumanTranslationReviewStatus(Enum):
    """Explicit human disposition, separate from automated review priority."""

    UNREVIEWED = "unreviewed"
    ACCEPTED = "accepted"
    EDITED_VERIFIED = "edited_verified"
    FLAGGED = "flagged"


class TranslationReviewWarningCode(Enum):
    """Stable identifiers for observable review-warning signals."""

    TRANSLATION_FAILED = "translation_failed"
    SOURCE_COPY_SIMILARITY = "source_copy_similarity"
    NUMERIC_MISMATCH = "numeric_mismatch"
    STRUCTURE_MISMATCH = "structure_mismatch"


def review_status_display(status: TranslationReviewStatus) -> str:
    """Return the stable human-facing label for one review status."""

    return {
        TranslationReviewStatus.NORMAL_REVIEW: "Normal Review",
        TranslationReviewStatus.REVIEW_RECOMMENDED: "Review Recommended",
        TranslationReviewStatus.TRANSLATION_FAILED: "Translation Failed",
    }[status]


def human_review_status_display(status: HumanTranslationReviewStatus) -> str:
    """Return the stable human-facing label for a human review disposition."""

    return {
        HumanTranslationReviewStatus.UNREVIEWED: "Unreviewed",
        HumanTranslationReviewStatus.ACCEPTED: "Accepted",
        HumanTranslationReviewStatus.EDITED_VERIFIED: "Edited / Verified",
        HumanTranslationReviewStatus.FLAGGED: "Flagged",
    }[status]


def _immutable_context(context: Mapping[str, Any]) -> Mapping[str, Any]:
    """Copy compact warning context into an immutable mapping."""

    return MappingProxyType(dict(context))


@dataclass(frozen=True)
class TranslationReviewWarning:
    """One reproducible signal that may help prioritize human review."""

    code: TranslationReviewWarningCode
    explanation: str
    context: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not isinstance(self.code, TranslationReviewWarningCode):
            raise ValueError("code must be a TranslationReviewWarningCode.")
        if not isinstance(self.explanation, str) or not self.explanation.strip():
            raise ValueError("explanation is required.")
        object.__setattr__(self, "context", _immutable_context(self.context))


@dataclass(frozen=True)
class TranslationReviewAssessment:
    """Immutable assessment of observable signals for one translation result."""

    request_id: str
    status: TranslationReviewStatus
    warnings: tuple[TranslationReviewWarning, ...] = ()
    revision: str = ASSESSMENT_REVISION

    def __post_init__(self) -> None:
        if not isinstance(self.request_id, str) or not self.request_id.strip():
            raise ValueError("request_id is required.")
        if not isinstance(self.status, TranslationReviewStatus):
            raise ValueError("status must be a TranslationReviewStatus.")
        if not isinstance(self.warnings, tuple) or any(
                not isinstance(warning, TranslationReviewWarning) for warning in self.warnings):
            raise ValueError("warnings must be a tuple of TranslationReviewWarning values.")
        if not isinstance(self.revision, str) or not self.revision.strip():
            raise ValueError("revision is required.")
        codes = tuple(warning.code for warning in self.warnings)
        if len(codes) != len(set(codes)):
            raise ValueError("warning codes must be unique.")
        if self.status is TranslationReviewStatus.NORMAL_REVIEW and self.warnings:
            raise ValueError("normal review assessments cannot contain warnings.")
        if self.status is TranslationReviewStatus.TRANSLATION_FAILED and codes != (TranslationReviewWarningCode.TRANSLATION_FAILED,):
            raise ValueError("failed assessments require only the translation_failed warning.")


@dataclass(frozen=True)
class HumanTranslationReview:
    """Immutable human review evidence that never replaces provider output."""

    request_id: str
    status: HumanTranslationReviewStatus = HumanTranslationReviewStatus.UNREVIEWED
    verified_translation: str | None = None
    reviewer_notes: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.request_id, str) or not self.request_id.strip():
            raise ValueError("request_id is required.")
        if not isinstance(self.status, HumanTranslationReviewStatus):
            raise ValueError("status must be a HumanTranslationReviewStatus.")
        if self.status is HumanTranslationReviewStatus.EDITED_VERIFIED:
            if not isinstance(self.verified_translation, str) or not self.verified_translation.strip():
                raise ValueError("Edited / Verified reviews require verified_translation.")
        elif self.verified_translation is not None:
            raise ValueError("verified_translation is only valid for Edited / Verified reviews.")
        if self.reviewer_notes is not None and not isinstance(self.reviewer_notes, str):
            raise ValueError("reviewer_notes must be text when supplied.")


@dataclass(frozen=True)
class ReviewedTranslationResolution:
    """One resolved output decision without changing any underlying evidence."""

    request_id: str
    human_review_status: HumanTranslationReviewStatus
    translation_status: TranslationStatus
    output_text: str | None
    human_verified: bool


def resolve_reviewed_translation(
        translation_status: TranslationStatus,
        original_ai_translation: str | None,
        human_review: HumanTranslationReview) -> ReviewedTranslationResolution:
    """Resolve reviewed output centrally while preserving OCR and provider text."""

    if not isinstance(translation_status, TranslationStatus):
        raise ValueError("translation_status must be a TranslationStatus.")
    if not isinstance(human_review, HumanTranslationReview):
        raise ValueError("human_review must be a HumanTranslationReview.")
    if translation_status is TranslationStatus.SUCCESS:
        if not isinstance(original_ai_translation, str) or not original_ai_translation.strip():
            raise ValueError("Successful resolution requires original_ai_translation.")
    elif original_ai_translation is not None:
        raise ValueError("Failed resolution cannot contain original_ai_translation.")
    if translation_status is TranslationStatus.FAILURE:
        return ReviewedTranslationResolution(
            human_review.request_id, human_review.status, translation_status, None, False)
    if human_review.status is HumanTranslationReviewStatus.EDITED_VERIFIED:
        return ReviewedTranslationResolution(
            human_review.request_id, human_review.status, translation_status,
            human_review.verified_translation, True)
    if human_review.status is HumanTranslationReviewStatus.ACCEPTED:
        return ReviewedTranslationResolution(
            human_review.request_id, human_review.status, translation_status,
            original_ai_translation, True)
    return ReviewedTranslationResolution(
        human_review.request_id, human_review.status, translation_status,
        original_ai_translation, False)


def _words(text: str) -> tuple[str, ...]:
    """Normalize textual words for conservative same-language copying checks."""

    return tuple(word.casefold() for word in _WORD_TOKEN.findall(text))


def _numeric_tokens(text: str) -> tuple[str, ...]:
    """Return numeric evidence without attempting numeric interpretation."""

    return tuple(token.replace(",", ".") for token in _NUMBER_TOKEN.findall(text))


def _source_copy_warning(result: TranslationResult) -> TranslationReviewWarning | None:
    """Flag only substantial near-identical source/translation evidence."""

    source, translated = result.source_text, result.translated_text or ""
    if _URL.search(source) or _URL.search(translated):
        return None
    source_words, translated_words = _words(source), _words(translated)
    if (len(source_words) < SOURCE_COPY_MINIMUM_WORDS or len(translated_words) < SOURCE_COPY_MINIMUM_WORDS
            or len("".join(source_words)) < SOURCE_COPY_MINIMUM_CHARACTERS):
        return None
    source_normalized, translated_normalized = " ".join(source_words), " ".join(translated_words)
    similarity = SequenceMatcher(None, source_normalized, translated_normalized, autojunk=False).ratio()
    if similarity >= SOURCE_COPY_SIMILARITY_THRESHOLD:
        return TranslationReviewWarning(
            TranslationReviewWarningCode.SOURCE_COPY_SIMILARITY,
            "Translation closely resembles source text.",
            {"similarity": similarity},
        )
    return None


def _numeric_warning(result: TranslationResult) -> TranslationReviewWarning | None:
    """Flag changed or missing numeric tokens without guessing conversions."""

    source_numbers = _numeric_tokens(result.source_text)
    translated_numbers = _numeric_tokens(result.translated_text or "")
    if source_numbers and Counter(source_numbers) != Counter(translated_numbers):
        return TranslationReviewWarning(
            TranslationReviewWarningCode.NUMERIC_MISMATCH,
            "Numeric tokens differ between source and translation.",
            {"source_numbers": source_numbers, "translation_numbers": translated_numbers},
        )
    return None


def _structure_warning(result: TranslationResult) -> TranslationReviewWarning | None:
    """Flag substantial observable line or list-structure loss only."""

    source_lines = tuple(line for line in result.source_text.splitlines() if line.strip())
    translated_lines = tuple(line for line in (result.translated_text or "").splitlines() if line.strip())
    source_bullets = sum(bool(_BULLET_LINE.match(line)) for line in source_lines)
    translated_bullets = sum(bool(_BULLET_LINE.match(line)) for line in translated_lines)
    line_loss = (len(source_lines) >= STRUCTURE_LOSS_MINIMUM_LINES
                 and len(translated_lines) <= len(source_lines) // 2)
    bullet_loss = source_bullets >= 2 and translated_bullets < source_bullets
    if line_loss or bullet_loss:
        return TranslationReviewWarning(
            TranslationReviewWarningCode.STRUCTURE_MISMATCH,
            "Translation may not preserve the source line or list structure.",
            {"source_line_count": len(source_lines), "translation_line_count": len(translated_lines),
             "source_bullet_count": source_bullets, "translation_bullet_count": translated_bullets},
        )
    return None


def assess_translation_result(result: TranslationResult) -> TranslationReviewAssessment:
    """Assess one result using only deterministic, already preserved evidence."""

    if not isinstance(result, TranslationResult):
        raise ValueError("result must be a TranslationResult.")
    if result.status is TranslationStatus.FAILURE:
        warning = TranslationReviewWarning(
            TranslationReviewWarningCode.TRANSLATION_FAILED,
            "No usable provider translation was produced.",
        )
        return TranslationReviewAssessment(result.request_id, TranslationReviewStatus.TRANSLATION_FAILED, (warning,))
    warnings = tuple(warning for warning in (
        _source_copy_warning(result), _numeric_warning(result), _structure_warning(result),
    ) if warning is not None)
    status = TranslationReviewStatus.REVIEW_RECOMMENDED if warnings else TranslationReviewStatus.NORMAL_REVIEW
    return TranslationReviewAssessment(result.request_id, status, warnings)


def assess_translation_results(results: Iterable[TranslationResult]) -> tuple[TranslationReviewAssessment, ...]:
    """Assess results in supplied order and reject duplicate request evidence."""

    assessments = tuple(assess_translation_result(result) for result in results)
    identifiers = tuple(assessment.request_id for assessment in assessments)
    if len(identifiers) != len(set(identifiers)):
        raise ValueError("translation results must not contain duplicate request IDs.")
    return assessments
