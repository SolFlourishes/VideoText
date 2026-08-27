"""Immutable translation-job scope and provider-neutral output preferences.

This module describes what a translation run intends to cover. It deliberately
contains neither source text nor provider instances: text evidence continues to
belong to ``TranslationSourceRecord`` and provider invocation belongs to the
translation pipeline.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from string import Formatter
from types import MappingProxyType
from typing import Any, Mapping

from translation_contract import _validate_language
from translation_provider_registry import normalize_provider_name


_TEMPLATE_FIELDS = frozenset({
    "job_id", "source_id", "source_display_name", "source_base_name",
    "target_language", "target_language_display_name",
})


def _immutable_metadata(metadata: Mapping[str, Any]) -> Mapping[str, Any]:
    """Return a copied, read-only metadata mapping."""

    return MappingProxyType(dict(metadata))


def _required(value: str, field_name: str) -> None:
    """Require a non-blank string domain identifier or label."""

    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} is required.")


def _validate_template(template: str | None, field_name: str) -> None:
    """Allow only the planner's fixed placeholder vocabulary."""

    if template is None:
        return
    _required(template, field_name)
    for _, name, format_spec, conversion in Formatter().parse(template):
        if name is not None and (name not in _TEMPLATE_FIELDS or format_spec or conversion):
            raise ValueError(f"{field_name} contains an unsupported placeholder.")


class TranslationOutputGrouping(Enum):
    """How a job's source-language pairs are grouped into workbooks."""

    BY_LANGUAGE = "by_language"
    BY_SOURCE = "by_source"
    COMBINED = "combined"
    SEPARATE = "separate"


class OutputCollisionPolicy(Enum):
    """Deterministic in-plan name collision behavior."""

    SUFFIX = "suffix"


@dataclass(frozen=True)
class TranslationSourceItem:
    """One ordered video or project item included in a translation job."""

    source_item_id: str
    display_name: str
    evidence_reference: str
    ordering_index: int
    original_filename: str | None = None
    output_base_name: str | None = None

    def __post_init__(self) -> None:
        _required(self.source_item_id, "source_item_id")
        _required(self.display_name, "display_name")
        _required(self.evidence_reference, "evidence_reference")
        if not isinstance(self.ordering_index, int) or self.ordering_index < 0:
            raise ValueError("ordering_index must be a non-negative integer.")
        for value, name in ((self.original_filename, "original_filename"), (self.output_base_name, "output_base_name")):
            if value is not None:
                _required(value, name)


@dataclass(frozen=True)
class TranslationOutputPlan:
    """Immutable grouping and controlled naming preferences for new workbooks."""

    grouping: TranslationOutputGrouping
    combined_workbook_name: str | None = None
    filename_template: str | None = None
    sheet_name_template: str | None = None
    collision_policy: OutputCollisionPolicy = OutputCollisionPolicy.SUFFIX
    batch_name: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.grouping, TranslationOutputGrouping):
            raise ValueError("grouping must be a TranslationOutputGrouping.")
        if self.combined_workbook_name is not None:
            _required(self.combined_workbook_name, "combined_workbook_name")
        _validate_template(self.filename_template, "filename_template")
        _validate_template(self.sheet_name_template, "sheet_name_template")
        if not isinstance(self.collision_policy, OutputCollisionPolicy):
            raise ValueError("collision_policy must be an OutputCollisionPolicy.")
        if self.batch_name is not None and not isinstance(self.batch_name, str):
            raise ValueError("batch_name must be a string or None.")


@dataclass(frozen=True)
class TranslationJob:
    """One immutable, deterministic translation scope without text or clients."""

    job_id: str
    source_items: tuple[TranslationSourceItem, ...]
    source_language: str
    target_languages: tuple[str, ...]
    provider_name: str
    output_plan: TranslationOutputPlan
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        _required(self.job_id, "job_id")
        if not isinstance(self.source_items, tuple):
            raise ValueError("source_items must be an immutable tuple.")
        if not self.source_items:
            raise ValueError("source_items must not be empty.")
        if any(not isinstance(item, TranslationSourceItem) for item in self.source_items):
            raise ValueError("source_items must contain TranslationSourceItem values.")
        source_ids = [item.source_item_id.casefold() for item in self.source_items]
        if len(source_ids) != len(set(source_ids)):
            raise ValueError("source_items must have unique source_item_id values.")
        _validate_language(self.source_language, "source_language")
        if not isinstance(self.target_languages, tuple):
            raise ValueError("target_languages must be an immutable tuple.")
        if not self.target_languages:
            raise ValueError("target_languages must not be empty.")
        for language in self.target_languages:
            _validate_language(language, "target_languages")
            if language.casefold() == self.source_language.casefold():
                raise ValueError("source_language and target_languages must differ.")
        normalized_targets = [language.casefold() for language in self.target_languages]
        if len(normalized_targets) != len(set(normalized_targets)):
            raise ValueError("target_languages must be unique after normalization.")
        object.__setattr__(self, "provider_name", normalize_provider_name(self.provider_name))
        if not isinstance(self.output_plan, TranslationOutputPlan):
            raise ValueError("output_plan must be a TranslationOutputPlan.")
        object.__setattr__(self, "metadata", _immutable_metadata(self.metadata))
