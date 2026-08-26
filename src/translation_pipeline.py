"""Deterministic downstream request construction and translation execution."""

from __future__ import annotations

from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any, Iterable, Mapping

from translation_contract import (
    TranslationProvenance,
    TranslationProvider,
    TranslationRequest,
    TranslationResult,
    TranslationSourceType,
    TranslationStatus,
)


def _immutable_metadata(metadata: Mapping[str, Any]) -> Mapping[str, Any]:
    """Copy source context into a read-only mapping."""

    return MappingProxyType(dict(metadata))


def _usable(text: str | None) -> bool:
    """Return whether text is present without changing the text itself."""

    return isinstance(text, str) and bool(text.strip())


@dataclass(frozen=True)
class TranslationSourceRecord:
    """One stable OCR-derived unit projected for downstream translation only.

    `source_reference` must be supplied by the canonical/review layer. It is
    deliberately not derived from spreadsheet rows or UI state.
    """

    source_reference: str
    canonical_ocr_text: str
    verified_ocr_text: str | None = None
    accepted_user_edited_text: str | None = None
    user_edit_accepted: bool = False
    ordering_index: int | None = None
    context: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not isinstance(self.source_reference, str) or not self.source_reference.strip():
            raise ValueError("source_reference is required.")
        if not isinstance(self.canonical_ocr_text, str):
            raise ValueError("canonical_ocr_text must be a string.")
        for name, value in (("verified_ocr_text", self.verified_ocr_text), ("accepted_user_edited_text", self.accepted_user_edited_text)):
            if value is not None and not isinstance(value, str):
                raise ValueError(f"{name} must be a string when supplied.")
        if not isinstance(self.user_edit_accepted, bool):
            raise ValueError("user_edit_accepted must be a boolean.")
        if self.ordering_index is not None and (not isinstance(self.ordering_index, int) or self.ordering_index < 0):
            raise ValueError("ordering_index must be a non-negative integer when provided.")
        object.__setattr__(self, "context", _immutable_metadata(self.context))


def build_translation_request(
    record: TranslationSourceRecord,
    source_language: str,
    target_language: str,
) -> TranslationRequest | None:
    """Select one source deterministically, returning no request for empty evidence."""

    if _usable(record.verified_ocr_text):
        selected_text = record.verified_ocr_text
        source_type = TranslationSourceType.VERIFIED_OCR
    elif record.user_edit_accepted and _usable(record.accepted_user_edited_text):
        selected_text = record.accepted_user_edited_text
        source_type = TranslationSourceType.USER_EDIT
    elif _usable(record.canonical_ocr_text):
        selected_text = record.canonical_ocr_text
        source_type = TranslationSourceType.OCR
    else:
        return None
    return TranslationRequest(
        request_id=f"{record.source_reference}:translation:{target_language}",
        source_text=selected_text,
        source_language=source_language,
        target_language=target_language,
        provenance=TranslationProvenance(record.source_reference, source_type, record.context),
        ordering_index=record.ordering_index,
    )


def build_translation_requests(
    records: Iterable[TranslationSourceRecord], source_language: str, target_language: str,
) -> tuple[TranslationRequest, ...]:
    """Build requests in supplied evidence order, skipping only unusable records."""

    return tuple(
        request for record in records
        if (request := build_translation_request(record, source_language, target_language)) is not None
    )


@dataclass(frozen=True)
class TranslationBatchResult:
    """Ordered outcomes from one sequential, failure-contained translation pass."""

    results: tuple[TranslationResult, ...]

    @property
    def submitted_count(self) -> int:
        return len(self.results)

    @property
    def success_count(self) -> int:
        return sum(result.status is TranslationStatus.SUCCESS for result in self.results)

    @property
    def failure_count(self) -> int:
        return sum(result.status is TranslationStatus.FAILURE for result in self.results)


def _provider_id(provider: TranslationProvider) -> str | None:
    """Read a safe provider identifier for a contained provider failure."""

    try:
        identifier = provider.provider_id
    except Exception:
        return None
    return identifier if isinstance(identifier, str) and identifier.strip() else None


def execute_translation_requests(
    requests: Iterable[TranslationRequest], provider: TranslationProvider,
    progress_callback=None,
) -> TranslationBatchResult:
    """Translate sequentially, converting only provider-boundary failures to results."""

    results: list[TranslationResult] = []
    provider_id = _provider_id(provider)
    ordered_requests = tuple(requests)
    for current, request in enumerate(ordered_requests, start=1):
        if not isinstance(request, TranslationRequest):
            raise ValueError("Translation execution requires TranslationRequest objects.")
        try:
            result = provider.translate(request)
            if not isinstance(result, TranslationResult):
                raise ValueError("Translation provider returned an invalid result.")
            if result.request is not request:
                raise ValueError("Translation provider returned a result for a different request.")
        except Exception as error:
            result = TranslationResult(
                request=request,
                status=TranslationStatus.FAILURE,
                provider_id=provider_id,
                error=f"{type(error).__name__}: {error}",
            )
        results.append(result)
        if progress_callback is not None:
            progress_callback(current, len(ordered_requests))
    return TranslationBatchResult(tuple(results))
