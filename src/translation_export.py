"""Provider-neutral downstream translation CSV, Markdown, and Excel exports."""

from __future__ import annotations

import csv
import re
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Iterable, Mapping

from translation_contract import TranslationResult, TranslationSourceType, TranslationStatus
from translation_job import TranslationJob
from translation_output_plan import (
    TranslationOutputLayout,
    language_display_name,
    sanitize_filename_label,
)
from translation_review import (HumanTranslationReview, TranslationReviewAssessment,
    TranslationReviewStatus, assess_translation_results, resolve_reviewed_translation,
    review_status_display)
from translation_workbook import (
    TranslationWorkbookRow, TranslationWorkbookWriteResult,
    _safe_error, populate_translation_workbooks,
)


_SAFE_FILENAME = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
_CSV_HEADERS = (
    "Source Item", "Slide", "Original Text", "Target Language",
    "Initial AI Translation", "Translation Status", "Provider", "Model",
    "Request ID", "Source Reference", "Source Type", "Error",
    "Review Status", "Review Warnings",
)


@dataclass(frozen=True)
class TranslationExportRecord:
    """One immutable consumable projection of completed translation evidence."""

    source_item_id: str
    source_item_name: str
    slide_value: int | str
    source_reference: str
    source_type: TranslationSourceType
    original_text: str
    target_language: str
    initial_ai_translation: str | None
    translation_status: TranslationStatus
    provider_id: str | None
    model_id: str | None
    request_id: str
    ordering_index: int
    error: str | None
    review_assessment: TranslationReviewAssessment
    human_review: HumanTranslationReview | None = None

    def __post_init__(self) -> None:
        if self.translation_status is TranslationStatus.SUCCESS and not self.initial_ai_translation:
            raise ValueError("Successful translation export records require initial_ai_translation.")
        if self.translation_status is TranslationStatus.FAILURE and self.initial_ai_translation is not None:
            raise ValueError("Failed translation export records cannot contain initial_ai_translation.")
        if not isinstance(self.review_assessment, TranslationReviewAssessment):
            raise ValueError("review_assessment must be a TranslationReviewAssessment.")
        if self.review_assessment.request_id != self.request_id:
            raise ValueError("Review assessment does not match the translation request.")
        if self.human_review is None:
            object.__setattr__(self, "human_review", HumanTranslationReview(self.request_id))
        elif not isinstance(self.human_review, HumanTranslationReview):
            raise ValueError("human_review must be a HumanTranslationReview.")
        elif self.human_review.request_id != self.request_id:
            raise ValueError("Human review does not match the translation request.")

    @property
    def reviewed_translation(self) -> str | None:
        """Return centrally resolved output text without mutating source evidence."""

        return resolve_reviewed_translation(
            self.translation_status, self.initial_ai_translation, self.human_review).output_text

    @property
    def human_verified_translation(self) -> str | None:
        """Return verified text without changing the preserved AI translation."""

        resolution = resolve_reviewed_translation(
            self.translation_status, self.initial_ai_translation, self.human_review)
        return resolution.output_text if resolution.human_verified else None


@dataclass(frozen=True)
class TranslationExportWriteResult:
    """Immutable summary of newly written downstream translation artifacts."""

    paths: Mapping[str, tuple[Path, ...]]
    record_count: int
    success_count: int
    failure_count: int
    source_count: int
    language_count: int

    def __post_init__(self) -> None:
        object.__setattr__(self, "paths", MappingProxyType({key: tuple(value) for key, value in self.paths.items()}))


def _assessment_map(assessments: Iterable[TranslationReviewAssessment], request_ids: set[str]) -> dict[str, TranslationReviewAssessment]:
    """Validate assessment identity without recalculating review signals."""

    mapped: dict[str, TranslationReviewAssessment] = {}
    for assessment in assessments:
        if not isinstance(assessment, TranslationReviewAssessment):
            raise ValueError("assessments must contain TranslationReviewAssessment values.")
        if assessment.request_id in mapped:
            raise ValueError(f"Duplicate translation review assessment: {assessment.request_id}.")
        mapped[assessment.request_id] = assessment
    if set(mapped) != request_ids:
        identifier = sorted((request_ids - set(mapped)) or (set(mapped) - request_ids))[0]
        raise ValueError(f"Translation review assessment does not match result: {identifier}.")
    return mapped


def build_translation_export_records(job: TranslationJob, source_rows: Iterable[TranslationWorkbookRow],
                                     translation_results: Iterable[TranslationResult],
                                     assessments: Iterable[TranslationReviewAssessment] | None = None) -> tuple[TranslationExportRecord, ...]:
    """Strictly project completed results in job source/language/row order."""

    source_order = {item.source_item_id: index for index, item in enumerate(job.source_items)}
    source_names = {item.source_item_id: item.display_name for item in job.source_items}
    language_order = {language: index for index, language in enumerate(job.target_languages)}
    rows: dict[str, TranslationWorkbookRow] = {}
    for row in source_rows:
        if not isinstance(row, TranslationWorkbookRow):
            raise ValueError("source_rows must contain TranslationWorkbookRow values.")
        if row.source_item_id not in source_order or row.target_language not in language_order:
            raise ValueError("Translation workbook row does not belong to the job.")
        if row.request_id in rows:
            raise ValueError(f"Duplicate expected translation request: {row.request_id}.")
        rows[row.request_id] = row
    results: dict[str, TranslationResult] = {}
    for result in translation_results:
        if not isinstance(result, TranslationResult):
            raise ValueError("translation_results must contain TranslationResult values.")
        if result.request_id in results:
            raise ValueError(f"Duplicate translation result for request: {result.request_id}.")
        results[result.request_id] = result
    if set(rows) != set(results):
        missing = set(rows) - set(results)
        extra = set(results) - set(rows)
        identifier = sorted(missing or extra)[0]
        kind = "Missing" if missing else "Translation result does not belong to the job"
        raise ValueError(f"{kind}: {identifier}.")
    assessment_map = _assessment_map(
        assess_translation_results(results.values()) if assessments is None else assessments,
        set(results),
    )
    records: list[TranslationExportRecord] = []
    for request_id, row in rows.items():
        result = results[request_id]
        request = result.request
        if (request.target_language != row.target_language or request.provenance.source_reference != row.source_reference
                or request.source_text != row.original_text):
            raise ValueError(f"Translation result does not match source evidence: {request_id}.")
        records.append(TranslationExportRecord(
            row.source_item_id, source_names[row.source_item_id], row.slide_value,
            row.source_reference, request.provenance.source_type, row.original_text,
            row.target_language, result.translated_text, result.status, result.provider_id,
            result.model_id, request_id, row.ordering_index, _safe_error(result.error), assessment_map[request_id],
        ))
    return tuple(sorted(records, key=lambda record: (
        source_order[record.source_item_id], language_order[record.target_language], record.ordering_index,
    )))


def _write_new_text(path: str | Path, content: str) -> Path:
    """Write one UTF-8 artifact only when its explicit destination is new."""

    if not isinstance(path, (str, Path)) or not str(path).strip():
        raise ValueError("output_path is required.")
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    try:
        with output.open("x", encoding="utf-8", newline="") as file:
            file.write(content)
    except FileExistsError as error:
        raise FileExistsError(f"Translation export already exists: {output}") from error
    return output


def export_translation_csv(records: Iterable[TranslationExportRecord], output_path: str | Path) -> Path:
    """Write a UTF-8, one-row-per-result CSV without replacing an existing file."""

    rows = tuple(records)
    for record in rows:
        if not isinstance(record, TranslationExportRecord):
            raise ValueError("records must contain TranslationExportRecord values.")
    if not isinstance(output_path, (str, Path)) or not str(output_path).strip():
        raise ValueError("output_path is required.")
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    try:
        with output.open("x", encoding="utf-8", newline="") as file:
            writer = csv.writer(file)
            writer.writerow(_CSV_HEADERS)
            for record in rows:
                writer.writerow((record.source_item_name, record.slide_value, record.original_text,
                    record.target_language, record.initial_ai_translation or "", record.translation_status.value,
                    record.provider_id or "", record.model_id or "", record.request_id,
                    record.source_reference, record.source_type.value, record.error or "",
                    review_status_display(record.review_assessment.status),
                    "; ".join(warning.code.value for warning in record.review_assessment.warnings)))
    except FileExistsError as error:
        raise FileExistsError(f"Translation export already exists: {output}") from error
    return output


def export_translation_markdown(records: Iterable[TranslationExportRecord], output_path: str | Path) -> Path:
    """Write accessible source-language sections from immutable export records."""

    content = ["# Translation Export", "", "All AI-generated translations require human review.", ""]
    previous_pair: tuple[str, str] | None = None
    for record in records:
        pair = (record.source_item_id, record.target_language)
        if pair != previous_pair:
            content.extend((f"## {record.source_item_name} — {language_display_name(record.target_language)}", ""))
            previous_pair = pair
        content.extend((f"### Slide {record.slide_value}", "", "**Original Text**", "", record.original_text, "",
                        "**Initial AI Translation**", "", record.initial_ai_translation or "", ""))
        review = record.review_assessment
        if record.translation_status is TranslationStatus.FAILURE:
            content.extend(("**Translation Status:** Failed", "", f"**Error:** {record.error or 'Translation failed.'}", ""))
        else:
            content.extend(("**Translation Status:** Success", ""))
        if review.status is not TranslationReviewStatus.NORMAL_REVIEW:
            content.extend((f"**Review Status:** {review_status_display(review.status)}", ""))
            for warning in review.warnings:
                content.extend((f"- {warning.explanation}",))
            content.append("")
        content.extend(("**Provenance**", "", f"- Target language: {record.target_language}",
                        f"- Provider: {record.provider_id or ''}", f"- Model: {record.model_id or ''}",
                        f"- Source type: {record.source_type.value}", f"- Source reference: {record.source_reference}",
                        f"- Request ID: {record.request_id}", ""))
    return _write_new_text(output_path, "\n".join(content))


def _text_export_path(directory: Path, job: TranslationJob, extension: str) -> Path:
    batch_name = sanitize_filename_label(job.output_plan.batch_name)
    if batch_name:
        return directory / f"{batch_name} - Translation{extension}"
    stem = _SAFE_FILENAME.sub("-", job.job_id).strip(". ") or "translation-export"
    return directory / f"{stem}-translation{extension}"


def export_translation_outputs(job: TranslationJob, output_layout: TranslationOutputLayout,
                               source_rows: Iterable[TranslationWorkbookRow], translation_results: Iterable[TranslationResult],
                               output_directory: str | Path, formats: Iterable[str],
                               assessments: Iterable[TranslationReviewAssessment] | None = None) -> TranslationExportWriteResult:
    """Create selected new downstream formats without provider or OCR activity."""

    requested = tuple(formats)
    if not requested or len(set(requested)) != len(requested) or any(value not in {"csv", "markdown", "excel"} for value in requested):
        raise ValueError("formats must be a non-empty unique selection of csv, markdown, and excel.")
    if not isinstance(output_directory, (str, Path)) or not str(output_directory).strip():
        raise ValueError("output_directory is required.")
    directory = Path(output_directory)
    rows, results = tuple(source_rows), tuple(translation_results)
    calculated_assessments = tuple(assessments) if assessments is not None else assess_translation_results(results)
    records = build_translation_export_records(job, rows, results, calculated_assessments)
    paths: dict[str, tuple[Path, ...]] = {}
    for format_name in requested:
        if format_name == "csv":
            paths[format_name] = (export_translation_csv(records, _text_export_path(directory, job, ".csv")),)
        elif format_name == "markdown":
            paths[format_name] = (export_translation_markdown(records, _text_export_path(directory, job, ".md")),)
        else:
            result: TranslationWorkbookWriteResult = populate_translation_workbooks(
                job, output_layout, rows, results, directory, calculated_assessments)
            paths[format_name] = tuple(result.workbook_paths.values())
    return TranslationExportWriteResult(paths, len(records),
        sum(record.translation_status is TranslationStatus.SUCCESS for record in records),
        sum(record.translation_status is TranslationStatus.FAILURE for record in records),
        len({record.source_item_id for record in records}), len({record.target_language for record in records}))
