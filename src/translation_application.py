"""Application composition for optional post-OCR translation runs."""
from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable
from models import Presentation
from translation_contract import TranslationProvider
from translation_export import TranslationExportWriteResult, export_translation_outputs
from translation_job import TranslationJob, TranslationOutputPlan, TranslationOutputGrouping, TranslationSourceItem
from translation_output_plan import plan_translation_output
from translation_pipeline import TranslationSourceRecord, build_translation_request, execute_translation_requests
from translation_workbook import TranslationWorkbookRow
from translation_review import TranslationReviewAssessment, TranslationReviewStatus, assess_translation_results

@dataclass(frozen=True)
class TranslationApplicationSource:
    """One presentation selected by the application, without GUI state."""
    source_item: TranslationSourceItem
    presentation: Presentation

@dataclass(frozen=True)
class TranslationApplicationResult:
    """Completed optional translation evidence and its downstream artifacts."""
    job: TranslationJob
    export_result: TranslationExportWriteResult
    assessments: tuple[TranslationReviewAssessment, ...]

    @property
    def review_recommended_count(self) -> int:
        """Count review-prioritized results without treating normal review as verified."""

        return sum(assessment.status is TranslationReviewStatus.REVIEW_RECOMMENDED
                   for assessment in self.assessments)

def run_translation_job(job_id: str, sources: Iterable[TranslationApplicationSource], source_language: str,
                        target_languages: tuple[str, ...], provider: TranslationProvider,
                        grouping: TranslationOutputGrouping, formats: tuple[str, ...], output_directory: Path,
                        progress_callback: Callable[[int, int], None] | None = None) -> TranslationApplicationResult:
    """Select source evidence, translate sequentially, and export without OCR work."""
    ordered_sources = tuple(sources)
    job = TranslationJob(job_id, tuple(value.source_item for value in ordered_sources), source_language,
        target_languages, provider.provider_id, TranslationOutputPlan(grouping))
    records: list[TranslationSourceRecord] = []
    row_context: dict[str, tuple[str, int | str, int]] = {}
    for source in ordered_sources:
        for slide in source.presentation.slides:
            for paragraph_index, paragraph in enumerate(slide.paragraphs):
                reference = f"{source.source_item.source_item_id}:slide:{slide.slide_number}:paragraph:{paragraph_index}"
                record = TranslationSourceRecord(reference, paragraph.text, ordering_index=len(records))
                records.append(record)
                row_context[reference] = (source.source_item.source_item_id, slide.slide_number, record.ordering_index or 0)
    requests = []
    rows = []
    for language in job.target_languages:
        for record in records:
            request = build_translation_request(record, job.source_language, language)
            if request is not None:
                source_item_id, slide_value, index = row_context[record.source_reference]
                requests.append(request)
                rows.append(TranslationWorkbookRow(source_item_id, record.source_reference, request.request_id,
                    language, slide_value, request.source_text, index))
    results = execute_translation_requests(requests, provider, progress_callback=progress_callback)
    assessments = assess_translation_results(results.results)
    layout = plan_translation_output(job)
    exported = export_translation_outputs(job, layout, rows, results.results, output_directory, formats, assessments)
    return TranslationApplicationResult(job, exported, assessments)
