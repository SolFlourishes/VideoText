"""Versioned JSON persistence for completed visual-understanding jobs."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

from visual_candidate_detection import (
    VisualAnalysisTarget,
    VisualCandidateAssessment,
    VisualCandidateDisposition,
    VisualSelectionScope,
)
from visual_evidence import ProjectedVisualEvidence
from visual_understanding_contract import (
    VisualAnalysisRequest,
    VisualAnalysisStatus,
    VisualAnalysisWarning,
    VisualContentType,
    VisualDetectionSignal,
    VisualEvidenceReference,
    VisualOCRRegion,
    VisualRelationship,
    VisualUnderstandingResult,
    to_json_compatible,
)
from visual_understanding_pipeline import VisualUnderstandingJob, VisualUnderstandingJobResult


SCHEMA_NAME = "videotext.visual_understanding"
SCHEMA_VERSION = "1.0"
DOCUMENT_FILENAME = "visual_understanding.json"


class VisualUnderstandingStorageError(ValueError):
    """Raised when a visual-understanding document or evidence file is invalid."""


def _required_text(value: object, path: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise VisualUnderstandingStorageError(f"{path} must be a non-empty string.")
    return value


def _object(value: object, path: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise VisualUnderstandingStorageError(f"{path} must be a JSON object.")
    return value


def _array(value: object, path: str) -> list[Any]:
    if not isinstance(value, list):
        raise VisualUnderstandingStorageError(f"{path} must be a JSON array.")
    return value


def _integer(value: object, path: str, *, minimum: int = 0) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < minimum:
        raise VisualUnderstandingStorageError(f"{path} must be an integer of at least {minimum}.")
    return value


def _number(value: object, path: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise VisualUnderstandingStorageError(f"{path} must be a finite number.")
    value = float(value)
    if value != value or value in (float("inf"), float("-inf")):
        raise VisualUnderstandingStorageError(f"{path} must be a finite number.")
    return value


def _boolean(value: object, path: str) -> bool:
    if not isinstance(value, bool):
        raise VisualUnderstandingStorageError(f"{path} must be a boolean.")
    return value


def _required(mapping: Mapping[str, Any], names: tuple[str, ...], path: str) -> None:
    missing = [name for name in names if name not in mapping]
    if missing:
        raise VisualUnderstandingStorageError(
            f"{path} is missing required field(s): {', '.join(missing)}."
        )


def _enum(enum_type, value: object, path: str):
    if not isinstance(value, str):
        raise VisualUnderstandingStorageError(f"{path} must be a string enum value.")
    try:
        return enum_type(value)
    except ValueError as error:
        raise VisualUnderstandingStorageError(f"{path} has an invalid value: {value}.") from error


def _evidence_data(reference: VisualEvidenceReference) -> dict[str, Any]:
    return {
        "source_reference": reference.source_reference,
        "checkpoint_path": reference.checkpoint_path,
        "slide_number": reference.slide_number,
        "build_index": reference.build_index,
        "frame_number": reference.frame_number,
        "timestamp": reference.timestamp,
        "image_width": reference.image_width,
        "image_height": reference.image_height,
        "authoritative_image_sha256": reference.authoritative_image_sha256,
        "submitted_image_sha256": reference.submitted_image_sha256,
        "submitted_image_width": reference.submitted_image_width,
        "submitted_image_height": reference.submitted_image_height,
        "image_transport_revision": reference.image_transport_revision,
    }


def _region_data(region: VisualOCRRegion) -> dict[str, Any]:
    return {
        "source_index": region.source_index,
        "text": region.text,
        "confidence": region.confidence,
        "bounding_box": list(region.bounding_box),
    }


def _signal_data(signal: VisualDetectionSignal) -> dict[str, Any]:
    return {
        "code": signal.code,
        "explanation": signal.explanation,
        "observed_values": to_json_compatible(signal.observed_values),
        "detector_revision": signal.detector_revision,
    }


def visual_evidence_relative_path(reference: VisualEvidenceReference) -> Path:
    """Return the canonical workspace-relative path for stored frame evidence."""

    if not isinstance(reference, VisualEvidenceReference):
        raise ValueError("reference must be a VisualEvidenceReference.")
    build = "none" if reference.build_index is None else f"{reference.build_index:04d}"
    digest = reference.submitted_image_sha256 or reference.authoritative_image_sha256
    return Path("evidence") / (
        f"slide_{reference.slide_number:04d}_build_{build}_"
        f"frame_{reference.frame_number:06d}_{digest[:12]}.png"
    )


def _request_data(request: VisualAnalysisRequest, evidence_path: str) -> dict[str, Any]:
    return {
        "request_id": request.request_id,
        "evidence": _evidence_data(request.evidence),
        "evidence_image_path": evidence_path,
        "image_media_type": request.image_media_type,
        "ocr_text": request.ocr_text,
        "ocr_regions": [_region_data(region) for region in request.ocr_regions],
        "detection_signals": [_signal_data(signal) for signal in request.detection_signals],
        "prompt_schema_revision": request.prompt_schema_revision,
        "interpretation_language": request.interpretation_language,
    }


def _target_data(target: VisualAnalysisTarget, index: int, evidence_path: str) -> dict[str, Any]:
    return {
        "target_index": index,
        "evidence": _evidence_data(target.evidence.reference),
        "evidence_image_path": evidence_path,
        "image_media_type": target.evidence.image_media_type,
        "ocr_text": target.evidence.ocr_text,
        "ocr_regions": [_region_data(region) for region in target.evidence.ocr_regions],
        "assessment": {
            "disposition": target.assessment.disposition.value,
            "reasons": list(target.assessment.reasons),
            "signals": [_signal_data(signal) for signal in target.assessment.signals],
            "detector_revision": target.assessment.detector_revision,
            "explanation": target.assessment.explanation,
        },
    }


def _result_data(result: VisualUnderstandingResult, index: int, evidence_path: str) -> dict[str, Any]:
    return {
        "target_index": index,
        "request": _request_data(result.request, evidence_path),
        "status": result.status.value,
        "provider_id": result.provider_id,
        "model_id": result.model_id,
        "content_type": None if result.content_type is None else result.content_type.value,
        "description": result.description,
        "relationships": [
            {"subject": item.subject, "relation": item.relation, "object": item.object}
            for item in result.relationships
        ],
        "structured_details": to_json_compatible(result.structured_details),
        "warnings": [
            {
                "code": warning.code,
                "message": warning.message,
                "details": to_json_compatible(warning.details),
            }
            for warning in result.warnings
        ],
        "error": result.error,
        "provider_metadata": to_json_compatible(result.provider_metadata),
    }


def _document(result: VisualUnderstandingJobResult) -> tuple[dict[str, Any], dict[str, bytes]]:
    if not isinstance(result, VisualUnderstandingJobResult):
        raise ValueError("result must be a VisualUnderstandingJobResult.")
    images: dict[str, bytes] = {}
    paths: list[str] = []
    for target in result.job.targets:
        reference = target.evidence.reference
        image_bytes = target.evidence.image_bytes
        expected_hash = reference.submitted_image_sha256 or reference.authoritative_image_sha256
        if hashlib.sha256(image_bytes).hexdigest() != expected_hash:
            raise VisualUnderstandingStorageError(
                f"Evidence image bytes do not match the recorded SHA-256 for frame {reference.frame_number}."
            )
        relative_path = visual_evidence_relative_path(reference).as_posix()
        if relative_path in images and images[relative_path] != image_bytes:
            raise VisualUnderstandingStorageError(f"Evidence filename collision: {relative_path}.")
        images[relative_path] = image_bytes
        paths.append(relative_path)
    document = {
        "schema_name": SCHEMA_NAME,
        "schema_version": SCHEMA_VERSION,
        "application_version": result.job.application_version,
        "job": {
            "job_id": result.job.job_id,
            "selection_scope": result.job.scope.value,
            "provider_id": result.job.provider_id,
            "interpretation_language": result.job.interpretation_language,
            "prompt_schema_revision": result.job.prompt_schema_revision,
            "cancelled": result.cancelled,
            "submitted_count": result.submitted_count,
            "success_count": result.success_count,
            "failure_count": result.failure_count,
            "unsubmitted_count": result.unsubmitted_count,
        },
        "targets": [
            _target_data(target, index, paths[index])
            for index, target in enumerate(result.job.targets)
        ],
        "results": [
            _result_data(item, index, paths[index])
            for index, item in enumerate(result.results)
        ],
    }
    # Enforce strict JSON values before touching the destination workspace.
    json.dumps(document, ensure_ascii=False, allow_nan=False)
    return document, images


def write_visual_understanding_result(
    result: VisualUnderstandingJobResult,
    workspace: str | Path,
    *,
    overwrite: bool = False,
) -> Path:
    """Write one explicit workspace without silently replacing prior evidence."""

    document, images = _document(result)
    workspace_path = Path(workspace)
    json_path = workspace_path / "cache" / DOCUMENT_FILENAME
    if json_path.exists() and not overwrite:
        raise FileExistsError(f"Visual-understanding result already exists: {json_path}")

    for relative_path, image_bytes in images.items():
        image_path = workspace_path / Path(relative_path)
        if image_path.exists() and image_path.read_bytes() != image_bytes:
            raise FileExistsError(
                f"Existing evidence image differs from the canonical bytes: {image_path}"
            )

    (workspace_path / "cache").mkdir(parents=True, exist_ok=True)
    (workspace_path / "evidence").mkdir(parents=True, exist_ok=True)
    for relative_path, image_bytes in images.items():
        image_path = workspace_path / Path(relative_path)
        if not image_path.exists():
            try:
                with image_path.open("xb") as image_file:
                    image_file.write(image_bytes)
            except FileExistsError:
                if image_path.read_bytes() != image_bytes:
                    raise FileExistsError(
                        f"Existing evidence image differs from the canonical bytes: {image_path}"
                    )

    payload = json.dumps(
        document,
        ensure_ascii=False,
        allow_nan=False,
        indent=2,
        sort_keys=False,
    ) + "\n"
    mode = "w" if overwrite else "x"
    with json_path.open(mode, encoding="utf-8", newline="\n") as output_file:
        output_file.write(payload)
    return json_path


def _resolve_document_path(source: str | Path) -> Path:
    path = Path(source)
    return path / "cache" / DOCUMENT_FILENAME if path.is_dir() else path


def _load_json(path: Path) -> dict[str, Any]:
    def reject_constant(value: str):
        raise VisualUnderstandingStorageError(f"JSON contains unsupported numeric value: {value}.")

    try:
        with path.open(encoding="utf-8") as source_file:
            value = json.load(source_file, parse_constant=reject_constant)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise VisualUnderstandingStorageError(
            f"Visual-understanding JSON could not be loaded: {type(error).__name__}: {error}"
        ) from error
    return _object(value, "document")


def _parse_evidence(value: object, path: str) -> VisualEvidenceReference:
    data = _object(value, path)
    _required(data, (
        "source_reference", "checkpoint_path", "slide_number", "build_index",
        "frame_number", "timestamp", "image_width", "image_height",
        "authoritative_image_sha256", "submitted_image_sha256",
    ), path)
    checkpoint = data["checkpoint_path"]
    build_index = data["build_index"]
    if checkpoint is not None:
        checkpoint = _required_text(checkpoint, f"{path}.checkpoint_path")
    if build_index is not None:
        build_index = _integer(build_index, f"{path}.build_index")
    try:
        return VisualEvidenceReference(
            source_reference=_required_text(data["source_reference"], f"{path}.source_reference"),
            checkpoint_path=checkpoint,
            slide_number=_integer(data["slide_number"], f"{path}.slide_number", minimum=1),
            build_index=build_index,
            frame_number=_integer(data["frame_number"], f"{path}.frame_number"),
            timestamp=_number(data["timestamp"], f"{path}.timestamp"),
            image_width=_integer(data["image_width"], f"{path}.image_width", minimum=1),
            image_height=_integer(data["image_height"], f"{path}.image_height", minimum=1),
            authoritative_image_sha256=_required_text(
                data["authoritative_image_sha256"], f"{path}.authoritative_image_sha256"
            ),
            submitted_image_sha256=(
                None if data["submitted_image_sha256"] is None else _required_text(
                    data["submitted_image_sha256"], f"{path}.submitted_image_sha256"
                )
            ),
            submitted_image_width=(
                None if data.get("submitted_image_width") is None else _integer(
                    data["submitted_image_width"], f"{path}.submitted_image_width", minimum=1
                )
            ),
            submitted_image_height=(
                None if data.get("submitted_image_height") is None else _integer(
                    data["submitted_image_height"], f"{path}.submitted_image_height", minimum=1
                )
            ),
            image_transport_revision=(
                None if data.get("image_transport_revision") is None else _required_text(
                    data["image_transport_revision"], f"{path}.image_transport_revision"
                )
            ),
        )
    except ValueError as error:
        raise VisualUnderstandingStorageError(f"{path} is invalid: {error}") from error


def _parse_regions(value: object, path: str) -> tuple[VisualOCRRegion, ...]:
    regions = []
    for index, item in enumerate(_array(value, path)):
        item_path = f"{path}[{index}]"
        data = _object(item, item_path)
        _required(data, ("source_index", "text", "confidence", "bounding_box"), item_path)
        box = _array(data["bounding_box"], f"{item_path}.bounding_box")
        if len(box) != 4:
            raise VisualUnderstandingStorageError(f"{item_path}.bounding_box must contain four values.")
        try:
            regions.append(VisualOCRRegion(
                source_index=_integer(data["source_index"], f"{item_path}.source_index"),
                text=data["text"] if isinstance(data["text"], str) else _required_text(None, f"{item_path}.text"),
                confidence=_number(data["confidence"], f"{item_path}.confidence"),
                bounding_box=tuple(_number(value, f"{item_path}.bounding_box") for value in box),
            ))
        except ValueError as error:
            raise VisualUnderstandingStorageError(f"{item_path} is invalid: {error}") from error
    return tuple(regions)


def _parse_signals(value: object, path: str) -> tuple[VisualDetectionSignal, ...]:
    signals = []
    for index, item in enumerate(_array(value, path)):
        item_path = f"{path}[{index}]"
        data = _object(item, item_path)
        _required(data, ("code", "explanation", "observed_values", "detector_revision"), item_path)
        try:
            signals.append(VisualDetectionSignal(
                code=_required_text(data["code"], f"{item_path}.code"),
                explanation=_required_text(data["explanation"], f"{item_path}.explanation"),
                observed_values=_object(data["observed_values"], f"{item_path}.observed_values"),
                detector_revision=_required_text(
                    data["detector_revision"], f"{item_path}.detector_revision"
                ),
            ))
        except ValueError as error:
            raise VisualUnderstandingStorageError(f"{item_path} is invalid: {error}") from error
    return tuple(signals)


def _evidence_bytes(
    document_path: Path,
    relative_value: object,
    reference: VisualEvidenceReference,
    path: str,
    verify: bool,
) -> tuple[str, bytes]:
    relative = _required_text(relative_value, path)
    relative_path = Path(relative)
    if relative_path.is_absolute() or ".." in relative_path.parts:
        raise VisualUnderstandingStorageError(f"{path} must be a safe relative path.")
    workspace = document_path.parent.parent
    image_path = workspace / relative_path
    try:
        image_bytes = image_path.read_bytes()
    except OSError as error:
        raise VisualUnderstandingStorageError(
            f"Evidence image could not be loaded: {image_path}: {type(error).__name__}: {error}"
        ) from error
    if verify:
        expected = reference.submitted_image_sha256 or reference.authoritative_image_sha256
        actual = hashlib.sha256(image_bytes).hexdigest()
        if actual != expected:
            raise VisualUnderstandingStorageError(
                f"Evidence image SHA-256 mismatch: {image_path}."
            )
    return relative, image_bytes


def _parse_target(
    value: object,
    index: int,
    document_path: Path,
    verify_evidence: bool,
) -> tuple[VisualAnalysisTarget, str]:
    path = f"targets[{index}]"
    data = _object(value, path)
    _required(data, (
        "target_index", "evidence", "evidence_image_path", "image_media_type",
        "ocr_text", "ocr_regions", "assessment",
    ), path)
    if _integer(data["target_index"], f"{path}.target_index") != index:
        raise VisualUnderstandingStorageError(f"{path}.target_index must preserve target ordering.")
    reference = _parse_evidence(data["evidence"], f"{path}.evidence")
    relative, image_bytes = _evidence_bytes(
        document_path, data["evidence_image_path"], reference,
        f"{path}.evidence_image_path", verify_evidence,
    )
    media_type = _required_text(data["image_media_type"], f"{path}.image_media_type")
    if media_type != "image/png":
        raise VisualUnderstandingStorageError(f"{path}.image_media_type must be image/png.")
    ocr_text = data["ocr_text"]
    if not isinstance(ocr_text, str):
        raise VisualUnderstandingStorageError(f"{path}.ocr_text must be a string.")
    regions = _parse_regions(data["ocr_regions"], f"{path}.ocr_regions")
    assessment_data = _object(data["assessment"], f"{path}.assessment")
    _required(assessment_data, (
        "disposition", "reasons", "signals", "detector_revision", "explanation",
    ), f"{path}.assessment")
    reasons_value = _array(assessment_data["reasons"], f"{path}.assessment.reasons")
    reasons = tuple(
        _required_text(reason, f"{path}.assessment.reasons[{reason_index}]")
        for reason_index, reason in enumerate(reasons_value)
    )
    signals = _parse_signals(assessment_data["signals"], f"{path}.assessment.signals")
    assessment = VisualCandidateAssessment(
        disposition=_enum(
            VisualCandidateDisposition,
            assessment_data["disposition"],
            f"{path}.assessment.disposition",
        ),
        reasons=reasons,
        signals=signals,
        detector_revision=_required_text(
            assessment_data["detector_revision"], f"{path}.assessment.detector_revision"
        ),
        explanation=assessment_data["explanation"] if isinstance(
            assessment_data["explanation"], str
        ) else _required_text(None, f"{path}.assessment.explanation"),
    )
    return VisualAnalysisTarget(
        ProjectedVisualEvidence(reference, image_bytes, media_type, ocr_text, regions),
        assessment,
    ), relative


def _same_evidence(first: VisualEvidenceReference, second: VisualEvidenceReference) -> bool:
    return first == second


def _parse_result(
    value: object,
    index: int,
    target: VisualAnalysisTarget,
    target_image_path: str,
    document_path: Path,
    verify_evidence: bool,
) -> VisualUnderstandingResult:
    path = f"results[{index}]"
    data = _object(value, path)
    _required(data, (
        "target_index", "request", "status", "provider_id", "model_id", "content_type",
        "description", "relationships", "structured_details", "warnings", "error",
        "provider_metadata",
    ), path)
    if _integer(data["target_index"], f"{path}.target_index") != index:
        raise VisualUnderstandingStorageError(f"{path}.target_index must preserve result ordering.")
    request_data = _object(data["request"], f"{path}.request")
    _required(request_data, (
        "request_id", "evidence", "evidence_image_path", "image_media_type", "ocr_text",
        "ocr_regions", "detection_signals", "prompt_schema_revision", "interpretation_language",
    ), f"{path}.request")
    request_reference = _parse_evidence(request_data["evidence"], f"{path}.request.evidence")
    if not _same_evidence(request_reference, target.evidence.reference):
        raise VisualUnderstandingStorageError(f"{path}.request evidence does not match its target.")
    request_relative, request_bytes = _evidence_bytes(
        document_path, request_data["evidence_image_path"], request_reference,
        f"{path}.request.evidence_image_path", verify_evidence,
    )
    if request_relative != target_image_path or request_bytes != target.evidence.image_bytes:
        raise VisualUnderstandingStorageError(f"{path}.request evidence image does not match its target.")
    request_regions = _parse_regions(request_data["ocr_regions"], f"{path}.request.ocr_regions")
    request_signals = _parse_signals(
        request_data["detection_signals"], f"{path}.request.detection_signals"
    )
    if request_regions != target.evidence.ocr_regions or request_signals != target.assessment.signals:
        raise VisualUnderstandingStorageError(f"{path}.request OCR/signals do not match its target.")
    ocr_text = request_data["ocr_text"]
    if not isinstance(ocr_text, str) or ocr_text != target.evidence.ocr_text:
        raise VisualUnderstandingStorageError(f"{path}.request.ocr_text does not match its target.")
    language = request_data["interpretation_language"]
    if language is not None:
        language = _required_text(language, f"{path}.request.interpretation_language")
    try:
        request = VisualAnalysisRequest(
            request_id=_required_text(request_data["request_id"], f"{path}.request.request_id"),
            evidence=target.evidence.reference,
            image_bytes=target.evidence.image_bytes,
            image_media_type=_required_text(
                request_data["image_media_type"], f"{path}.request.image_media_type"
            ),
            ocr_text=ocr_text,
            ocr_regions=request_regions,
            detection_signals=request_signals,
            prompt_schema_revision=_required_text(
                request_data["prompt_schema_revision"], f"{path}.request.prompt_schema_revision"
            ),
            interpretation_language=language,
        )
    except ValueError as error:
        raise VisualUnderstandingStorageError(f"{path}.request is invalid: {error}") from error

    relationships = []
    for relation_index, item in enumerate(_array(data["relationships"], f"{path}.relationships")):
        item_path = f"{path}.relationships[{relation_index}]"
        relation = _object(item, item_path)
        _required(relation, ("subject", "relation", "object"), item_path)
        relationships.append(VisualRelationship(
            _required_text(relation["subject"], f"{item_path}.subject"),
            _required_text(relation["relation"], f"{item_path}.relation"),
            _required_text(relation["object"], f"{item_path}.object"),
        ))
    warnings = []
    for warning_index, item in enumerate(_array(data["warnings"], f"{path}.warnings")):
        item_path = f"{path}.warnings[{warning_index}]"
        warning = _object(item, item_path)
        _required(warning, ("code", "message", "details"), item_path)
        warnings.append(VisualAnalysisWarning(
            _required_text(warning["code"], f"{item_path}.code"),
            _required_text(warning["message"], f"{item_path}.message"),
            _object(warning["details"], f"{item_path}.details"),
        ))
    provider_id = data["provider_id"]
    model_id = data["model_id"]
    content_type_value = data["content_type"]
    description = data["description"]
    error_value = data["error"]
    for current, name in ((provider_id, "provider_id"), (model_id, "model_id"),
                          (description, "description"), (error_value, "error")):
        if current is not None and not isinstance(current, str):
            raise VisualUnderstandingStorageError(f"{path}.{name} must be a string or null.")
    try:
        return VisualUnderstandingResult(
            request=request,
            status=_enum(VisualAnalysisStatus, data["status"], f"{path}.status"),
            provider_id=provider_id,
            model_id=model_id,
            content_type=(
                None if content_type_value is None else _enum(
                    VisualContentType, content_type_value, f"{path}.content_type"
                )
            ),
            description=description,
            relationships=tuple(relationships),
            structured_details=_object(data["structured_details"], f"{path}.structured_details"),
            warnings=tuple(warnings),
            error=error_value,
            provider_metadata=_object(data["provider_metadata"], f"{path}.provider_metadata"),
        )
    except ValueError as error:
        raise VisualUnderstandingStorageError(f"{path} is invalid: {error}") from error


def load_visual_understanding_result(
    source: str | Path,
    *,
    verify_evidence: bool = True,
) -> VisualUnderstandingJobResult:
    """Load schema 1.0 into immutable domain objects and optionally verify PNG hashes."""

    document_path = _resolve_document_path(source)
    document = _load_json(document_path)
    _required(document, (
        "schema_name", "schema_version", "application_version", "job", "targets", "results",
    ), "document")
    if document["schema_name"] != SCHEMA_NAME:
        raise VisualUnderstandingStorageError(
            f"Unsupported visual-understanding schema name: {document['schema_name']}.")
    if document["schema_version"] != SCHEMA_VERSION:
        raise VisualUnderstandingStorageError(
            f"Unsupported visual-understanding schema version: {document['schema_version']}.")
    application_version = _required_text(document["application_version"], "application_version")
    job_data = _object(document["job"], "job")
    _required(job_data, (
        "job_id", "selection_scope", "provider_id", "interpretation_language",
        "prompt_schema_revision", "cancelled", "submitted_count", "success_count",
        "failure_count", "unsubmitted_count",
    ), "job")
    target_values = _array(document["targets"], "targets")
    if not target_values:
        raise VisualUnderstandingStorageError("targets must contain at least one target.")
    parsed_targets = [
        _parse_target(value, index, document_path, verify_evidence)
        for index, value in enumerate(target_values)
    ]
    targets = tuple(value[0] for value in parsed_targets)
    language = job_data["interpretation_language"]
    if language is not None:
        language = _required_text(language, "job.interpretation_language")
    try:
        job = VisualUnderstandingJob(
            job_id=_required_text(job_data["job_id"], "job.job_id"),
            targets=targets,
            scope=_enum(VisualSelectionScope, job_data["selection_scope"], "job.selection_scope"),
            provider_id=_required_text(job_data["provider_id"], "job.provider_id"),
            interpretation_language=language,
            prompt_schema_revision=_required_text(
                job_data["prompt_schema_revision"], "job.prompt_schema_revision"
            ),
            application_version=application_version,
        )
    except ValueError as error:
        raise VisualUnderstandingStorageError(f"job is invalid: {error}") from error
    if job.targets != targets:
        raise VisualUnderstandingStorageError("targets are not stored in deterministic job order.")
    result_values = _array(document["results"], "results")
    if len(result_values) > len(targets):
        raise VisualUnderstandingStorageError("results cannot exceed targets.")
    results = tuple(
        _parse_result(
            value, index, targets[index], parsed_targets[index][1],
            document_path, verify_evidence,
        )
        for index, value in enumerate(result_values)
    )
    try:
        loaded = VisualUnderstandingJobResult(
            job=job,
            results=results,
            cancelled=_boolean(job_data["cancelled"], "job.cancelled"),
        )
    except ValueError as error:
        raise VisualUnderstandingStorageError(f"job result is invalid: {error}") from error
    recorded_counts = {
        "submitted_count": loaded.submitted_count,
        "success_count": loaded.success_count,
        "failure_count": loaded.failure_count,
        "unsubmitted_count": loaded.unsubmitted_count,
    }
    for name, actual in recorded_counts.items():
        if _integer(job_data[name], f"job.{name}") != actual:
            raise VisualUnderstandingStorageError(
                f"job.{name} does not match stored targets/results."
            )
    return loaded
