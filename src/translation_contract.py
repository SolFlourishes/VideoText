"""Provider-neutral, immutable translation domain objects.

Translation is downstream evidence.  These objects preserve the selected source
text and its provenance; providers may add a translation but never replace OCR
or verified source evidence.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
import re
from types import MappingProxyType
from typing import Any, Mapping, Protocol, runtime_checkable


_LANGUAGE_IDENTIFIER = re.compile(r"^[A-Za-z]{2,3}(?:-[A-Za-z0-9]{2,8})*$")


class TranslationSourceType(Enum):
    """The evidence layer from which translation source text was selected."""

    OCR = "ocr"
    VERIFIED_OCR = "verified_ocr"
    USER_EDIT = "user_edit"


class TranslationStatus(Enum):
    """The outcome of one provider translation attempt."""

    SUCCESS = "success"
    FAILURE = "failure"


def _immutable_metadata(metadata: Mapping[str, Any]) -> Mapping[str, Any]:
    """Copy metadata into a read-only mapping without changing its values."""

    return MappingProxyType(dict(metadata))


def _validate_language(value: str, field_name: str) -> None:
    """Require a compact BCP 47-style language identifier."""

    if not isinstance(value, str) or not _LANGUAGE_IDENTIFIER.fullmatch(value):
        raise ValueError(f"{field_name} must be a valid language identifier.")


@dataclass(frozen=True)
class TranslationProvenance:
    """Immutable reference to the evidence selected as translation source."""

    source_reference: str
    source_type: TranslationSourceType
    context: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not isinstance(self.source_reference, str) or not self.source_reference.strip():
            raise ValueError("source_reference is required.")
        if not isinstance(self.source_type, TranslationSourceType):
            raise ValueError("source_type must be a TranslationSourceType.")
        object.__setattr__(self, "context", _immutable_metadata(self.context))


@dataclass(frozen=True)
class TranslationRequest:
    """One immutable source-text unit submitted to a translation provider."""

    request_id: str
    source_text: str
    source_language: str
    target_language: str
    provenance: TranslationProvenance
    ordering_index: int | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.request_id, str) or not self.request_id.strip():
            raise ValueError("request_id is required.")
        if not isinstance(self.source_text, str) or not self.source_text.strip():
            raise ValueError("source_text is required.")
        _validate_language(self.source_language, "source_language")
        _validate_language(self.target_language, "target_language")
        if self.source_language.casefold() == self.target_language.casefold():
            raise ValueError("source_language and target_language must differ.")
        if not isinstance(self.provenance, TranslationProvenance):
            raise ValueError("provenance must be a TranslationProvenance.")
        if self.ordering_index is not None and (not isinstance(self.ordering_index, int) or self.ordering_index < 0):
            raise ValueError("ordering_index must be a non-negative integer when provided.")


@dataclass(frozen=True)
class TranslationResult:
    """Immutable provider outcome that retains, rather than replaces, its request."""

    request: TranslationRequest
    status: TranslationStatus
    provider_id: str | None
    translated_text: str | None = None
    model_id: str | None = None
    error: str | None = None
    provider_metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not isinstance(self.request, TranslationRequest):
            raise ValueError("request must be a TranslationRequest.")
        if not isinstance(self.status, TranslationStatus):
            raise ValueError("status must be a TranslationStatus.")
        if self.provider_id is not None and (not isinstance(self.provider_id, str) or not self.provider_id.strip()):
            raise ValueError("provider_id must be non-empty when supplied.")
        if self.status is TranslationStatus.SUCCESS:
            if not self.provider_id:
                raise ValueError("provider_id is required for a successful translation.")
            if not isinstance(self.translated_text, str) or not self.translated_text.strip():
                raise ValueError("translated_text is required for a successful translation.")
            if self.error is not None:
                raise ValueError("successful translations cannot include an error.")
        else:
            if self.translated_text is not None:
                raise ValueError("failed translations cannot contain translated_text.")
            if not isinstance(self.error, str) or not self.error.strip():
                raise ValueError("error is required for a failed translation.")
        object.__setattr__(self, "provider_metadata", _immutable_metadata(self.provider_metadata))

    @property
    def request_id(self) -> str:
        """Expose the stable request identifier without duplicating source data."""

        return self.request.request_id

    @property
    def source_text(self) -> str:
        """Expose the original immutable source text for consumers and reports."""

        return self.request.source_text


@runtime_checkable
class TranslationProvider(Protocol):
    """Minimal provider-neutral translation boundary for local or cloud adapters."""

    @property
    def provider_id(self) -> str:
        """Return the provider's stable identifier."""

    def translate(self, request: TranslationRequest) -> TranslationResult:
        """Translate one request and return an explicit success or failure result."""
