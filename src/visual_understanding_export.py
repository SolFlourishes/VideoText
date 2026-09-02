"""Human-readable Markdown export for persisted visual-understanding results."""

from __future__ import annotations

import json
import html
from pathlib import Path
import re
from typing import Any

from visual_understanding_contract import VisualAnalysisStatus, to_json_compatible
from visual_understanding_pipeline import VisualUnderstandingJobResult
from visual_understanding_store import visual_evidence_relative_path


REPORT_FILENAME = "visual-understanding.md"
_FENCE_RUN = re.compile(r"`+")


def _display(value: object | None) -> str:
    return "Not specified" if value is None or value == "" else str(value)


def _inline_code(value: object | None) -> str:
    text = _display(value).replace("\r", " ").replace("\n", " ")
    longest = max((len(match.group()) for match in _FENCE_RUN.finditer(text)), default=0)
    delimiter = "`" * max(1, longest + 1)
    padding = " " if text.startswith("`") or text.endswith("`") else ""
    return f"{delimiter}{padding}{text}{padding}{delimiter}"


def _block(text: str, language: str = "text") -> list[str]:
    longest = max((len(match.group()) for match in _FENCE_RUN.finditer(text)), default=0)
    fence = "`" * max(3, longest + 1)
    return [f"{fence}{language}", text, fence, ""]


def _json_block(value: Any) -> list[str]:
    text = json.dumps(to_json_compatible(value), ensure_ascii=False, indent=2, sort_keys=True)
    return _block(text, "json")


def _heading_text(value: str) -> str:
    """Keep source identity readable without allowing it to create Markdown structure."""

    escaped = html.escape(value, quote=False)
    return escaped.replace("\\", "\\\\").replace("#", "\\#").replace("\r", " ").replace("\n", " ")


def _evidence_section(lines: list[str], target) -> None:
    reference = target.evidence.reference
    relative_path = visual_evidence_relative_path(reference).as_posix()
    lines.extend((
        "### Evidence", "",
        f"![Source frame]({relative_path})", "",
        f"- Source reference: {_inline_code(reference.source_reference)}",
        f"- Source/checkpoint: {_inline_code(reference.checkpoint_path)}",
        f"- Build: {_inline_code(reference.build_index)}",
        f"- Frame: {reference.frame_number}",
        f"- Timestamp: {reference.timestamp:g}s",
        f"- Image SHA-256: `{reference.authoritative_image_sha256}`",
    ))
    if reference.submitted_image_sha256 is not None:
        lines.append(f"- Submitted image SHA-256: `{reference.submitted_image_sha256}`")
    if reference.submitted_image_width is not None:
        lines.append(
            f"- Submitted image dimensions: {reference.submitted_image_width}x"
            f"{reference.submitted_image_height}"
        )
    if reference.image_transport_revision is not None:
        lines.append(f"- Image transport revision: `{reference.image_transport_revision}`")
    lines.extend(("", "### OCR Context", ""))
    lines.extend(_block(target.evidence.ocr_text))
    lines.extend(("### Candidate Signals", "",
                  "These are observable deterministic triage signals, not semantic conclusions or calibrated confidence.", ""))
    assessment = target.assessment
    lines.extend((f"- Disposition: `{assessment.disposition.value}`",
                  f"- Detector revision: {_inline_code(assessment.detector_revision)}"))
    if assessment.explanation:
        lines.append(f"- Assessment: {_inline_code(assessment.explanation)}")
    if assessment.reasons:
        lines.append(f"- Reason codes: {', '.join(_inline_code(item) for item in assessment.reasons)}")
    for signal in assessment.signals:
        observed = json.dumps(to_json_compatible(signal.observed_values), ensure_ascii=False, sort_keys=True)
        lines.append(
            f"- {_inline_code(signal.code)} — {_inline_code(signal.explanation)} "
            f"(observed: {_inline_code(observed)}; detector: {_inline_code(signal.detector_revision)})"
        )
    if not assessment.signals:
        lines.append("- No deterministic signals recorded.")
    lines.append("")


def _result_section(lines: list[str], result) -> None:
    lines.extend(("### AI-Derived Visual Interpretation", "",
                  "This section is provider-derived interpretation and is not preserved source truth.", "",
                  f"- Status: **{result.status.value.title()}**",
                  f"- Provider: {_inline_code(result.provider_id)}",
                  f"- Model: {_inline_code(result.model_id)}",
                  f"- Prompt/schema revision: {_inline_code(result.request.prompt_schema_revision)}", ""))
    if result.status is VisualAnalysisStatus.FAILURE:
        lines.extend(("#### Safe Error", ""))
        lines.extend(_block(result.error or "Visual analysis failed."))
        return
    lines.extend((f"- Visual type: `{result.content_type.value}`", "", "#### Description", ""))
    lines.extend(_block(result.description or ""))
    lines.extend(("#### Relationships", ""))
    if result.relationships:
        for relationship in result.relationships:
            lines.append(
                f"- {_inline_code(relationship.subject)} — {_inline_code(relationship.relation)} → "
                f"{_inline_code(relationship.object)}"
            )
    else:
        lines.append("- None recorded.")
    lines.extend(("", "#### Structured Details", ""))
    lines.extend(_json_block(result.structured_details))
    lines.extend(("#### Warnings", ""))
    if result.warnings:
        for warning in result.warnings:
            details = json.dumps(to_json_compatible(warning.details), ensure_ascii=False, sort_keys=True)
            lines.append(
                f"- {_inline_code(warning.code)}: {_inline_code(warning.message)}; details: {_inline_code(details)}"
            )
    else:
        lines.append("- None recorded.")
    lines.append("")


def render_visual_understanding_markdown(result: VisualUnderstandingJobResult) -> str:
    """Render a report solely from immutable stored-domain data."""

    if not isinstance(result, VisualUnderstandingJobResult):
        raise ValueError("result must be a VisualUnderstandingJobResult.")
    job = result.job
    sources = tuple(dict.fromkeys(target.evidence.reference.source_reference for target in job.targets))
    models = tuple(dict.fromkeys(item.model_id for item in result.results if item.model_id))
    lines = [
        "# Visual Understanding Report", "",
        "AI-derived interpretations in this report are separate from preserved OCR and image evidence.", "",
        "## Analysis Summary", "",
        f"- Source(s): {', '.join(_inline_code(item) for item in sources)}",
        f"- Provider: {_inline_code(job.provider_id)}",
        f"- Model(s): {', '.join(_inline_code(item) for item in models) if models else 'Not specified'}",
        f"- Application version: {_inline_code(job.application_version)}",
        f"- Selection scope: `{job.scope.value}`",
        f"- Interpretation language: {_inline_code(job.interpretation_language)}",
        f"- Prompt/schema revision: {_inline_code(job.prompt_schema_revision)}", "",
        f"- Selected frames: {len(job.targets)}",
        f"- Submitted: {result.submitted_count}",
        f"- Succeeded: {result.success_count}",
        f"- Failed: {result.failure_count}",
        f"- Unsubmitted: {result.unsubmitted_count}",
        f"- Cancelled: {'Yes' if result.cancelled else 'No'}", "",
    ]
    previous_source = None
    for index, target in enumerate(job.targets):
        reference = target.evidence.reference
        if reference.source_reference != previous_source:
            lines.extend((f"## Source — {_heading_text(reference.source_reference)}", ""))
            previous_source = reference.source_reference
        build = "none" if reference.build_index is None else reference.build_index
        lines.extend((
            f"## Slide {reference.slide_number} — Build {build}, Frame {reference.frame_number} at {reference.timestamp:g}s",
            "",
        ))
        _evidence_section(lines, target)
        if index < len(result.results):
            _result_section(lines, result.results[index])
        else:
            lines.extend(("### AI-Derived Visual Interpretation", "",
                          "- Status: **Not submitted**", "",
                          "This selected frame was not submitted to the provider and is not a provider failure.", ""))
    return "\n".join(lines).rstrip() + "\n"


def write_visual_understanding_markdown(
    result_or_loaded_result: VisualUnderstandingJobResult,
    workspace: str | Path,
    *,
    overwrite: bool = False,
) -> Path:
    """Write one standalone UTF-8 report without touching stored evidence."""

    content = render_visual_understanding_markdown(result_or_loaded_result)
    output = Path(workspace) / REPORT_FILENAME
    output.parent.mkdir(parents=True, exist_ok=True)
    mode = "w" if overwrite else "x"
    try:
        with output.open(mode, encoding="utf-8", newline="\n") as report_file:
            report_file.write(content)
    except FileExistsError as error:
        raise FileExistsError(f"Visual-understanding report already exists: {output}") from error
    return output
