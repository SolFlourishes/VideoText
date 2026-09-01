"""Deterministic headless orchestration for selected visual-analysis targets."""

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Callable

from app_info import APP_RELEASE
from visual_candidate_detection import VisualAnalysisTarget, VisualSelectionScope
from visual_understanding_contract import (
    VisualAnalysisRequest,
    VisualAnalysisStatus,
    VisualUnderstandingProvider,
    VisualUnderstandingResult,
)


DEFAULT_VISUAL_PROMPT_SCHEMA_REVISION = "visual-understanding-v1"
_LANGUAGE_IDENTIFIER = re.compile(r"^[A-Za-z]{2,3}(?:-[A-Za-z0-9]{2,8})*$")


def _required_text(value: object, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} is required.")
    return value


def _target_key(target: VisualAnalysisTarget) -> tuple[str, int, int, int]:
    return (
        target.evidence.reference.source_reference,
        target.slide_number,
        -1 if target.build_index is None else target.build_index,
        target.frame_number,
    )


@dataclass(frozen=True)
class VisualUnderstandingJob:
    """Immutable deterministic scope for one provider-specific visual job."""

    job_id: str
    targets: tuple[VisualAnalysisTarget, ...]
    scope: VisualSelectionScope
    provider_id: str
    interpretation_language: str | None = None
    prompt_schema_revision: str = DEFAULT_VISUAL_PROMPT_SCHEMA_REVISION
    application_version: str = APP_RELEASE

    def __post_init__(self) -> None:
        _required_text(self.job_id, "job_id")
        _required_text(self.provider_id, "provider_id")
        _required_text(self.prompt_schema_revision, "prompt_schema_revision")
        _required_text(self.application_version, "application_version")
        if not isinstance(self.scope, VisualSelectionScope):
            raise ValueError("scope must be a VisualSelectionScope.")
        if not isinstance(self.targets, tuple) or any(
            not isinstance(target, VisualAnalysisTarget) for target in self.targets
        ):
            raise ValueError("targets must be a tuple of VisualAnalysisTarget values.")
        if not self.targets:
            raise ValueError("targets must contain at least one selected visual target.")
        if self.interpretation_language is not None and (
            not isinstance(self.interpretation_language, str)
            or not _LANGUAGE_IDENTIFIER.fullmatch(self.interpretation_language)
        ):
            raise ValueError("interpretation_language must be a language identifier when supplied.")
        ordered = tuple(sorted(self.targets, key=_target_key))
        identities = tuple(_target_key(target) for target in ordered)
        if len(identities) != len(set(identities)):
            raise ValueError("targets must not repeat the same slide/build/frame identity.")
        object.__setattr__(self, "targets", ordered)


@dataclass(frozen=True)
class VisualUnderstandingJobResult:
    """Ordered completed outcomes plus explicit cancellation/unsubmitted state."""

    job: VisualUnderstandingJob
    results: tuple[VisualUnderstandingResult, ...]
    cancelled: bool = False

    def __post_init__(self) -> None:
        if not isinstance(self.job, VisualUnderstandingJob):
            raise ValueError("job must be a VisualUnderstandingJob.")
        if not isinstance(self.results, tuple) or any(
            not isinstance(result, VisualUnderstandingResult) for result in self.results
        ):
            raise ValueError("results must be a tuple of VisualUnderstandingResult values.")
        if len(self.results) > len(self.job.targets):
            raise ValueError("results cannot exceed selected targets.")
        if not isinstance(self.cancelled, bool):
            raise ValueError("cancelled must be a boolean.")
        if not self.cancelled and len(self.results) != len(self.job.targets):
            raise ValueError("A completed job requires one result per selected target.")
        for index, result in enumerate(self.results):
            if result.evidence is not self.job.targets[index].evidence.reference:
                raise ValueError("Job results must preserve ordered target evidence identity.")

    @property
    def submitted_count(self) -> int:
        return len(self.results)

    @property
    def success_count(self) -> int:
        return sum(result.status is VisualAnalysisStatus.SUCCESS for result in self.results)

    @property
    def failure_count(self) -> int:
        return sum(result.status is VisualAnalysisStatus.FAILURE for result in self.results)

    @property
    def unsubmitted_count(self) -> int:
        return len(self.job.targets) - len(self.results)


def build_visual_analysis_request(
    job: VisualUnderstandingJob,
    target: VisualAnalysisTarget,
    ordering_index: int,
) -> VisualAnalysisRequest:
    """Build one request from detached evidence without re-encoding its image."""

    if not isinstance(job, VisualUnderstandingJob):
        raise ValueError("job must be a VisualUnderstandingJob.")
    if not isinstance(target, VisualAnalysisTarget):
        raise ValueError("target must be a VisualAnalysisTarget.")
    if not isinstance(ordering_index, int) or isinstance(ordering_index, bool) or ordering_index < 0:
        raise ValueError("ordering_index must be a non-negative integer.")
    if ordering_index >= len(job.targets) or job.targets[ordering_index] is not target:
        raise ValueError("target and ordering_index must identify the same ordered job target.")
    evidence = target.evidence
    reference = evidence.reference
    build_value = "none" if reference.build_index is None else str(reference.build_index)
    request_id = (
        f"{job.job_id}:visual:{ordering_index}:slide:{reference.slide_number}:"
        f"build:{build_value}:frame:{reference.frame_number}"
    )
    return VisualAnalysisRequest(
        request_id=request_id,
        evidence=reference,
        image_bytes=evidence.image_bytes,
        image_media_type=evidence.image_media_type,
        ocr_text=evidence.ocr_text,
        ocr_regions=evidence.ocr_regions,
        detection_signals=target.assessment.signals,
        prompt_schema_revision=job.prompt_schema_revision,
        interpretation_language=job.interpretation_language,
    )


def _provider_id(provider: VisualUnderstandingProvider) -> str:
    value = provider.provider_id
    return _required_text(value, "provider.provider_id")


def _failed_result(
    request: VisualAnalysisRequest,
    provider_id: str,
    explanation: str,
) -> VisualUnderstandingResult:
    return VisualUnderstandingResult(
        request=request,
        status=VisualAnalysisStatus.FAILURE,
        provider_id=provider_id,
        error=explanation,
    )


def _validated_provider_result(
    request: VisualAnalysisRequest,
    provider_id: str,
    value: object,
) -> VisualUnderstandingResult:
    if not isinstance(value, VisualUnderstandingResult):
        return _failed_result(request, provider_id, "Visual provider returned an incompatible result.")
    if value.request is not request:
        return _failed_result(request, provider_id, "Visual provider returned a result for different evidence.")
    if value.evidence is not request.evidence:
        return _failed_result(request, provider_id, "Visual provider changed the evidence identity.")
    if value.evidence.authoritative_image_sha256 != request.evidence.authoritative_image_sha256:
        return _failed_result(request, provider_id, "Visual provider changed the evidence hash.")
    if value.provider_id != provider_id:
        return _failed_result(request, provider_id, "Visual provider returned a mismatched provider identity.")
    return value


def run_visual_understanding_job(
    job: VisualUnderstandingJob,
    provider: VisualUnderstandingProvider,
    *,
    progress_callback: Callable[[int, int], None] | None = None,
    cancel_check: Callable[[], bool] | None = None,
) -> VisualUnderstandingJobResult:
    """Analyze selected targets sequentially with per-request failure containment."""

    if not isinstance(job, VisualUnderstandingJob):
        raise ValueError("job must be a VisualUnderstandingJob.")
    provider_id = _provider_id(provider)
    if provider_id != job.provider_id:
        raise ValueError("Supplied provider identity does not match the visual job.")
    total = len(job.targets)
    if progress_callback is not None:
        progress_callback(0, total)
    results: list[VisualUnderstandingResult] = []
    cancelled = False
    for ordering_index, target in enumerate(job.targets):
        if cancel_check is not None and cancel_check():
            cancelled = True
            break
        request = build_visual_analysis_request(job, target, ordering_index)
        try:
            value = provider.analyze(request)
            result = _validated_provider_result(request, provider_id, value)
        except Exception as error:
            result = _failed_result(
                request,
                provider_id,
                f"Visual provider request failed ({type(error).__name__}).",
            )
        results.append(result)
        if progress_callback is not None:
            progress_callback(len(results), total)
    return VisualUnderstandingJobResult(job, tuple(results), cancelled)
