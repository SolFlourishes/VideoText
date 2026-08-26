"""Pure, deterministic planning of translation workbook and sheet placement."""

from __future__ import annotations

import re
from dataclasses import dataclass

from translation_job import TranslationJob, TranslationOutputGrouping, TranslationSourceItem
from translation_settings import translation_locale_display_name


_WINDOWS_ILLEGAL = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
_SHEET_ILLEGAL = re.compile(r'[:\\/?*\[\]\x00-\x1f]')
_LANGUAGE_NAMES = {
    "en": "English", "es": "Spanish", "de": "German", "fr": "French",
    "it": "Italian", "pt": "Portuguese", "ja": "Japanese", "ko": "Korean",
    "zh": "Chinese", "ar": "Arabic",
}


@dataclass(frozen=True)
class PlannedSheet:
    """An ordered, not-yet-created sheet for one source-language pair."""

    sheet_id: str
    name: str
    source_item_id: str
    target_language: str
    ordering_index: int


@dataclass(frozen=True)
class PlannedWorkbook:
    """An ordered, not-yet-created workbook containing planned sheets."""

    workbook_id: str
    filename: str
    sheets: tuple[PlannedSheet, ...]
    source_item_ids: tuple[str, ...]
    target_languages: tuple[str, ...]


@dataclass(frozen=True)
class TranslationOutputLayout:
    """The complete immutable output layout for one translation job."""

    job_id: str
    workbooks: tuple[PlannedWorkbook, ...]


def language_display_name(language: str) -> str:
    """Return a stable display name without collapsing regional identifiers."""

    return translation_locale_display_name(_LANGUAGE_NAMES.get(language, language))


def _safe(value: str, pattern: re.Pattern[str], fallback: str, maximum: int | None = None) -> str:
    value = pattern.sub(" ", value).strip().rstrip(". ")
    value = re.sub(r"\s+", " ", value) or fallback
    if maximum is not None:
        value = value[:maximum].rstrip(". ") or fallback
    return value


def _filename(value: str) -> str:
    base_value = value[:-5] if value.casefold().endswith(".xlsx") else value
    base = _safe(base_value, _WINDOWS_ILLEGAL, "Translation")
    return f"{base}.xlsx"


def _unique_filename(preferred: str, used: set[str]) -> str:
    stem = preferred[:-5] if preferred.lower().endswith(".xlsx") else preferred
    candidate, suffix = f"{stem}.xlsx", 2
    while candidate.casefold() in used:
        ending = f" ({suffix})"
        candidate = f"{stem[: max(1, 240 - len(ending))].rstrip('. ')}{ending}.xlsx"
        suffix += 1
    used.add(candidate.casefold())
    return candidate


def _unique_sheet(preferred: str, used: set[str]) -> str:
    stem = _safe(preferred, _SHEET_ILLEGAL, "Translation", 31)
    candidate, suffix = stem, 2
    while candidate.casefold() in used:
        ending = f" ({suffix})"
        candidate = stem[: 31 - len(ending)].rstrip() + ending
        suffix += 1
    used.add(candidate.casefold())
    return candidate


def _values(job: TranslationJob, item: TranslationSourceItem, language: str) -> dict[str, str]:
    return {
        "job_id": job.job_id, "source_id": item.source_item_id,
        "source_display_name": item.display_name,
        "source_base_name": item.output_base_name or item.display_name,
        "target_language": language,
        "target_language_display_name": language_display_name(language),
    }


def _render(template: str | None, default: str, values: dict[str, str]) -> str:
    """Render only templates validated by ``TranslationOutputPlan``."""

    return (template or default).format_map(values)


def _sheet(job: TranslationJob, item: TranslationSourceItem, language: str, index: int, used: set[str], default: str) -> PlannedSheet:
    name = _unique_sheet(_render(job.output_plan.sheet_name_template, default, _values(job, item, language)), used)
    return PlannedSheet(f"{job.job_id}:sheet:{item.source_item_id}:{language}", name, item.source_item_id, language, index)


def plan_translation_output(job: TranslationJob) -> TranslationOutputLayout:
    """Plan names and placement only; no provider, file, or workbook is touched.

    Workbook IDs are ``<job>:workbook:language:<language>``,
    ``<job>:workbook:source:<source>``, ``<job>:workbook:combined``, or
    ``<job>:workbook:source:<source>:language:<language>``. A sheet ID is
    always ``<job>:sheet:<source>:<language>``.
    """

    workbooks: list[PlannedWorkbook] = []
    used_files: set[str] = set()
    index = 0

    def add(workbook_id: str, filename_default: str, sheets: list[PlannedSheet]) -> None:
        first = sheets[0]
        item = next(value for value in job.source_items if value.source_item_id == first.source_item_id)
        filename = _unique_filename(_filename(_render(job.output_plan.filename_template, filename_default, _values(job, item, first.target_language))), used_files)
        workbooks.append(PlannedWorkbook(workbook_id, filename, tuple(sheets),
            tuple(dict.fromkeys(sheet.source_item_id for sheet in sheets)),
            tuple(dict.fromkeys(sheet.target_language for sheet in sheets))))

    if job.output_plan.grouping is TranslationOutputGrouping.BY_LANGUAGE:
        for language in job.target_languages:
            used_sheets: set[str] = set()
            sheets = [_sheet(job, item, language, index + offset, used_sheets, item.display_name)
                      for offset, item in enumerate(job.source_items)]
            index += len(sheets)
            add(f"{job.job_id}:workbook:language:{language}", f"{language_display_name(language)}.xlsx", sheets)
    elif job.output_plan.grouping is TranslationOutputGrouping.BY_SOURCE:
        for item in job.source_items:
            used_sheets = set()
            sheets = [_sheet(job, item, language, index + offset, used_sheets, language_display_name(language))
                      for offset, language in enumerate(job.target_languages)]
            index += len(sheets)
            add(f"{job.job_id}:workbook:source:{item.source_item_id}", f"{item.output_base_name or item.display_name}.xlsx", sheets)
    elif job.output_plan.grouping is TranslationOutputGrouping.COMBINED:
        used_sheets: set[str] = set()
        sheets: list[PlannedSheet] = []
        for item in job.source_items:
            for language in job.target_languages:
                sheets.append(_sheet(job, item, language, index, used_sheets, f"{item.display_name} - {language_display_name(language)}"))
                index += 1
        add(f"{job.job_id}:workbook:combined", job.output_plan.combined_workbook_name or "Translation Batch.xlsx", sheets)
    else:
        for item in job.source_items:
            for language in job.target_languages:
                sheet = _sheet(job, item, language, index, set(), language_display_name(language))
                index += 1
                add(f"{job.job_id}:workbook:source:{item.source_item_id}:language:{language}", f"{item.output_base_name or item.display_name} - {language_display_name(language)}.xlsx", [sheet])
    return TranslationOutputLayout(job.job_id, tuple(workbooks))
