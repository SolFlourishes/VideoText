"""Headless, provider-neutral evaluation for VideoText visual understanding."""

from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import json
import math
from pathlib import Path
import re
import struct
from time import monotonic
from typing import Any, Callable, Iterable, Mapping

from visual_understanding_contract import (
    VisualAnalysisRequest,
    VisualAnalysisStatus,
    VisualContentType,
    VisualEvidenceReference,
    VisualRelationship,
    VisualUnderstandingProvider,
    VisualUnderstandingResult,
    freeze_json_value,
    to_json_compatible,
)
from visual_evidence import (
    CanonicalVisualImage,
    LOCAL_VISUAL_IMAGE_TRANSPORT_REVISION,
    LOCAL_VISUAL_MAXIMUM_IMAGE_DIMENSION,
    bounded_visual_image_transport,
)


EVALUATION_CASE_SCHEMA_VERSION = "visual-evaluation-case-v1"
EVALUATION_RESULT_SCHEMA_VERSION = "visual-evaluation-results-v1"
_CASE_ID = re.compile(r"^[a-z0-9][a-z0-9._-]*$")


class VisualEvaluationError(ValueError):
    """One deterministic case, evaluation, or output validation failure."""


def _unique_object(pairs):
    value = {}
    for key, item in pairs:
        if key in value:
            raise VisualEvaluationError(f"Duplicate JSON field: {key}.")
        value[key] = item
    return value


def _reject_constant(value: str):
    raise VisualEvaluationError(f"Unsupported JSON constant: {value}.")


def _required_text(value: object, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise VisualEvaluationError(f"{name} is required.")
    return value


def _relationship(value: object, name: str) -> VisualRelationship:
    if not isinstance(value, Mapping) or set(value) != {"subject", "relation", "object"}:
        raise VisualEvaluationError(f"{name} must contain subject, relation, and object.")
    try:
        return VisualRelationship(value["subject"], value["relation"], value["object"])
    except ValueError as error:
        raise VisualEvaluationError(f"{name} is invalid.") from error


@dataclass(frozen=True)
class VisualEvaluationCase:
    case_id: str
    category: str
    image_path: Path
    ocr_context: str
    allowed_content_types: tuple[VisualContentType, ...]
    required_relationships: tuple[VisualRelationship, ...] = ()
    allowed_relationships: tuple[VisualRelationship, ...] = ()
    required_details: Mapping[str, Any] = field(default_factory=dict)
    allowed_facts: tuple[str, ...] = ()
    prohibited_claims: tuple[str, ...] = ()
    expected_uncertainty: bool = False
    human_review_required: bool = False
    notes: str = ""

    def __post_init__(self) -> None:
        if not isinstance(self.case_id, str) or not _CASE_ID.fullmatch(self.case_id):
            raise VisualEvaluationError("case_id must be a stable lowercase identifier.")
        _required_text(self.category, "category")
        path = Path(self.image_path).resolve()
        if not path.is_file() or path.suffix.casefold() != ".png":
            raise VisualEvaluationError("image_path must identify an existing PNG file.")
        if not isinstance(self.ocr_context, str):
            raise VisualEvaluationError("ocr_context must be a string.")
        if not self.allowed_content_types or any(
            not isinstance(item, VisualContentType) for item in self.allowed_content_types
        ):
            raise VisualEvaluationError("allowed_content_types must contain approved values.")
        for name in ("required_relationships", "allowed_relationships"):
            if not isinstance(getattr(self, name), tuple) or any(
                not isinstance(item, VisualRelationship) for item in getattr(self, name)
            ):
                raise VisualEvaluationError(f"{name} must contain VisualRelationship values.")
        frozen = freeze_json_value(self.required_details, "required_details")
        if not isinstance(frozen, Mapping):
            raise VisualEvaluationError("required_details must be an object.")
        for name in ("allowed_facts", "prohibited_claims"):
            values = getattr(self, name)
            if not isinstance(values, tuple) or any(not isinstance(item, str) or not item.strip() for item in values):
                raise VisualEvaluationError(f"{name} must contain non-empty strings.")
        if not isinstance(self.expected_uncertainty, bool) or not isinstance(self.human_review_required, bool):
            raise VisualEvaluationError("uncertainty and human-review flags must be booleans.")
        if not isinstance(self.notes, str):
            raise VisualEvaluationError("notes must be a string.")
        object.__setattr__(self, "image_path", path)
        object.__setattr__(self, "required_details", frozen)


_CASE_FIELDS = {
    "schema_version", "case_id", "category", "image", "ocr_context",
    "allowed_content_types", "required_relationships", "allowed_relationships",
    "required_details", "allowed_facts", "prohibited_claims", "expected_uncertainty",
    "human_review_required", "notes",
}


def load_visual_evaluation_case(path: str | Path) -> VisualEvaluationCase:
    """Load one strict inspectable case without searching beyond its directory."""

    case_path = Path(path).resolve()
    try:
        document = json.loads(
            case_path.read_text(encoding="utf-8"),
            object_pairs_hook=_unique_object, parse_constant=_reject_constant,
        )
    except VisualEvaluationError:
        raise
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise VisualEvaluationError(f"Evaluation case could not be read: {case_path.name}.") from error
    if not isinstance(document, dict) or set(document) != _CASE_FIELDS:
        raise VisualEvaluationError("Evaluation case fields do not match schema v1.")
    if document["schema_version"] != EVALUATION_CASE_SCHEMA_VERSION:
        raise VisualEvaluationError("Unsupported evaluation-case schema version.")
    image_value = _required_text(document["image"], "image")
    image_path = (case_path.parent / image_value).resolve()
    if not image_path.is_relative_to(case_path.parent):
        raise VisualEvaluationError("Evaluation image must remain inside its case directory.")
    try:
        content_types = tuple(VisualContentType(item) for item in document["allowed_content_types"])
    except (TypeError, ValueError) as error:
        raise VisualEvaluationError("allowed_content_types contains an unsupported value.") from error
    for name in ("allowed_facts", "prohibited_claims"):
        if not isinstance(document[name], list):
            raise VisualEvaluationError(f"{name} must be an array.")
    if not isinstance(document["required_relationships"], list) or not isinstance(document["allowed_relationships"], list):
        raise VisualEvaluationError("Relationship expectations must be arrays.")
    return VisualEvaluationCase(
        case_id=document["case_id"], category=document["category"], image_path=image_path,
        ocr_context=document["ocr_context"], allowed_content_types=content_types,
        required_relationships=tuple(_relationship(item, "required_relationships") for item in document["required_relationships"]),
        allowed_relationships=tuple(_relationship(item, "allowed_relationships") for item in document["allowed_relationships"]),
        required_details=document["required_details"], allowed_facts=tuple(document["allowed_facts"]),
        prohibited_claims=tuple(document["prohibited_claims"]),
        expected_uncertainty=document["expected_uncertainty"],
        human_review_required=document["human_review_required"], notes=document["notes"],
    )


def load_visual_evaluation_cases(directory: str | Path) -> tuple[VisualEvaluationCase, ...]:
    root = Path(directory).resolve()
    if not root.is_dir():
        raise VisualEvaluationError("Evaluation-case directory does not exist.")
    paths = sorted(root.glob("*.json"), key=lambda item: item.name.casefold())
    if not paths:
        raise VisualEvaluationError("Evaluation-case directory contains no JSON cases.")
    cases = tuple(load_visual_evaluation_case(path) for path in paths)
    if len({case.case_id for case in cases}) != len(cases):
        raise VisualEvaluationError("Evaluation case IDs must be unique.")
    return cases


def _normalize(value: object) -> str:
    return " ".join(str(value).casefold().split())


def _relationship_key(value: VisualRelationship) -> tuple[str, str, str]:
    return (_normalize(value.subject), _normalize(value.relation), _normalize(value.object))


def _flatten_details(value: Any, prefix: str = "") -> dict[str, Any]:
    if isinstance(value, Mapping):
        answer: dict[str, Any] = {}
        for key, item in value.items():
            child = f"{prefix}.{key}" if prefix else key
            answer.update(_flatten_details(item, child))
        return answer
    return {prefix: value}


def _detail_matches(actual: Any, expected: Any) -> bool:
    if isinstance(actual, str) or isinstance(expected, str):
        return _normalize(actual) == _normalize(expected)
    return actual == expected


def _request_for_case(
    case: VisualEvaluationCase,
    maximum_image_dimension: int | None = LOCAL_VISUAL_MAXIMUM_IMAGE_DIMENSION,
) -> VisualAnalysisRequest:
    image = case.image_path.read_bytes()
    if len(image) < 24 or image[:8] != b"\x89PNG\r\n\x1a\n" or image[12:16] != b"IHDR":
        raise VisualEvaluationError(f"Evaluation image is not a valid PNG: {case.image_path.name}.")
    width, height = struct.unpack(">II", image[16:24])
    if width < 1 or height < 1:
        raise VisualEvaluationError(f"Evaluation PNG has invalid dimensions: {case.image_path.name}.")
    digest = hashlib.sha256(image).hexdigest()
    submitted = CanonicalVisualImage(image, "image/png", digest, width, height)
    if maximum_image_dimension is not None:
        submitted = bounded_visual_image_transport(
            submitted, maximum_dimension=maximum_image_dimension,
        )
    evidence = VisualEvidenceReference(
        source_reference=str(case.image_path), checkpoint_path=None, slide_number=1,
        build_index=None, frame_number=0, timestamp=0, image_width=width, image_height=height,
        authoritative_image_sha256=digest,
        submitted_image_sha256=submitted.sha256,
        submitted_image_width=submitted.width,
        submitted_image_height=submitted.height,
        image_transport_revision=(
            LOCAL_VISUAL_IMAGE_TRANSPORT_REVISION if submitted.sha256 != digest else None
        ),
    )
    return VisualAnalysisRequest(
        request_id=f"evaluation:{case.case_id}", evidence=evidence, image_bytes=submitted.png_bytes,
        image_media_type="image/png", ocr_text=case.ocr_context,
    )


def _failure_kind(result: VisualUnderstandingResult) -> str | None:
    if result.status is VisualAnalysisStatus.SUCCESS:
        return None
    value = (result.error or "").casefold()
    if "timeout" in value:
        return "timeout"
    if "refusal" in value or "declined" in value:
        return "refusal"
    if "structured" in value or "schema" in value or "malformed" in value:
        return "schema_invalid"
    return "provider_failure"


def _result_text(result: VisualUnderstandingResult) -> str:
    parts = [result.description or "", json.dumps(to_json_compatible(result.structured_details), ensure_ascii=False)]
    parts.extend(f"{item.subject} {item.relation} {item.object}" for item in result.relationships)
    return _normalize(" ".join(parts))


def evaluate_visual_case(case: VisualEvaluationCase, result: VisualUnderstandingResult, elapsed_seconds: float) -> dict[str, Any]:
    """Apply conservative deterministic checks; never produce a semantic score."""

    if result.request_id != f"evaluation:{case.case_id}":
        raise VisualEvaluationError("Provider result does not belong to the evaluation case.")
    success = result.status is VisualAnalysisStatus.SUCCESS
    returned = {_relationship_key(item): item for item in result.relationships}
    required = {_relationship_key(item): item for item in case.required_relationships}
    allowed = {_relationship_key(item): item for item in case.allowed_relationships}
    recovered = [required[key] for key in required if key in returned]
    missed = [required[key] for key in required if key not in returned]
    unsupported = [item for key, item in returned.items() if key not in required and key not in allowed]
    actual_details = _flatten_details(result.structured_details)
    missing_details = {
        path: to_json_compatible(expected) for path, expected in _flatten_details(case.required_details).items()
        if path not in actual_details or not _detail_matches(actual_details[path], expected)
    }
    result_text = _result_text(result)
    prohibited = [claim for claim in case.prohibited_claims if _normalize(claim) in result_text]
    warning_present = bool(result.warnings)
    return {
        "case_id": case.case_id, "category": case.category, "source_image": str(case.image_path),
        "authoritative_image_dimensions": [result.evidence.image_width, result.evidence.image_height],
        "authoritative_image_sha256": result.evidence.authoritative_image_sha256,
        "submitted_image_dimensions": [
            result.evidence.submitted_image_width or result.evidence.image_width,
            result.evidence.submitted_image_height or result.evidence.image_height,
        ],
        "submitted_image_sha256": (
            result.evidence.submitted_image_sha256 or result.evidence.authoritative_image_sha256
        ),
        "image_transport_revision": result.evidence.image_transport_revision,
        "ocr_context": case.ocr_context, "notes": case.notes,
        "human_review_required": case.human_review_required,
        "expected_uncertainty": case.expected_uncertainty,
        "elapsed_seconds": round(elapsed_seconds, 6), "structured_success": success,
        "failure_kind": _failure_kind(result),
        "content_type": result.content_type.value if result.content_type else None,
        "content_type_match": success and result.content_type in case.allowed_content_types,
        "required_relationship_count": len(required),
        "required_relationships_recovered": [_relationship_json(item) for item in recovered],
        "required_relationships_missed": [_relationship_json(item) for item in missed],
        "unsupported_relationships": [_relationship_json(item) for item in unsupported],
        "required_details_missing": missing_details,
        "prohibited_claims_detected": prohibited,
        "uncertainty_warning_expected": case.expected_uncertainty,
        "uncertainty_warning_present": warning_present,
        "expected": {
            "allowed_content_types": [item.value for item in case.allowed_content_types],
            "required_relationships": [_relationship_json(item) for item in case.required_relationships],
            "required_details": to_json_compatible(case.required_details),
            "allowed_facts": list(case.allowed_facts), "prohibited_claims": list(case.prohibited_claims),
        },
        "model_result": _result_json(result),
    }


def _relationship_json(item: VisualRelationship) -> dict[str, str]:
    return {"subject": item.subject, "relation": item.relation, "object": item.object}


def _result_json(result: VisualUnderstandingResult) -> dict[str, Any]:
    return {
        "status": result.status.value, "provider_id": result.provider_id, "model_id": result.model_id,
        "description": result.description, "relationships": [_relationship_json(item) for item in result.relationships],
        "structured_details": to_json_compatible(result.structured_details),
        "warnings": [{"code": item.code, "message": item.message, "details": to_json_compatible(item.details)} for item in result.warnings],
        "error": result.error, "provider_metadata": to_json_compatible(result.provider_metadata),
    }


def run_visual_evaluation(
    cases: Iterable[VisualEvaluationCase], provider: VisualUnderstandingProvider, *,
    startup_seconds: float = 0.0, runtime_metadata: Mapping[str, Any] | None = None,
    clock: Callable[[], float] = monotonic,
    maximum_image_dimension: int | None = LOCAL_VISUAL_MAXIMUM_IMAGE_DIMENSION,
) -> dict[str, Any]:
    """Evaluate ordered local cases sequentially through the provider contract."""

    ordered = tuple(cases)
    if not ordered:
        raise VisualEvaluationError("At least one evaluation case is required.")
    if len({case.case_id for case in ordered}) != len(ordered):
        raise VisualEvaluationError("Evaluation case IDs must be unique.")
    if isinstance(startup_seconds, bool) or not isinstance(startup_seconds, (int, float)) or not math.isfinite(startup_seconds) or startup_seconds < 0:
        raise VisualEvaluationError("startup_seconds must be a finite non-negative number.")
    started = clock()
    details = []
    for case in ordered:
        request = _request_for_case(case, maximum_image_dimension)
        request_started = clock()
        try:
            result = provider.analyze(request)
        except Exception as error:
            result = VisualUnderstandingResult(
                request=request, status=VisualAnalysisStatus.FAILURE,
                provider_id=provider.provider_id, error=f"provider_failure: {type(error).__name__}",
            )
        if not isinstance(result, VisualUnderstandingResult) or result.request is not request:
            result = VisualUnderstandingResult(
                request=request, status=VisualAnalysisStatus.FAILURE,
                provider_id=provider.provider_id, error="provider_failure: incompatible provider result",
            )
        elapsed = clock() - request_started
        details.append(evaluate_visual_case(case, result, elapsed))
    total_elapsed = clock() - started
    aggregate = _aggregate(details)
    provenance = dict(runtime_metadata or {})
    first_metadata = next((item["model_result"]["provider_metadata"] for item in details if item["model_result"]["provider_metadata"]), {})
    provenance.update(first_metadata)
    return {
        "schema_version": EVALUATION_RESULT_SCHEMA_VERSION,
        "provider_id": provider.provider_id,
        "model_id": next((item["model_result"]["model_id"] for item in details if item["model_result"]["model_id"]), None),
        "runtime_provenance": provenance,
        "performance": {"startup_seconds": round(float(startup_seconds), 6), "request_seconds": [item["elapsed_seconds"] for item in details], "total_evaluation_seconds": round(total_elapsed, 6)},
        "aggregate": aggregate, "cases": details,
    }


def _aggregate(details: list[dict[str, Any]]) -> dict[str, Any]:
    kinds = [item["failure_kind"] for item in details]
    return {
        "case_count": len(details), "requests_attempted": len(details),
        "structured_responses_succeeded": sum(item["structured_success"] for item in details),
        "failed_responses": sum(not item["structured_success"] for item in details),
        "schema_invalid_responses": kinds.count("schema_invalid"), "timeouts": kinds.count("timeout"),
        "refusals": kinds.count("refusal"),
        "content_type_matches": sum(item["content_type_match"] for item in details),
        "required_relationships_expected": sum(item["required_relationship_count"] for item in details),
        "required_relationships_recovered": sum(len(item["required_relationships_recovered"]) for item in details),
        "required_relationships_missed": sum(len(item["required_relationships_missed"]) for item in details),
        "unsupported_relationships_added": sum(len(item["unsupported_relationships"]) for item in details),
        "required_details_missed": sum(len(item["required_details_missing"]) for item in details),
        "prohibited_claims_detected": sum(len(item["prohibited_claims_detected"]) for item in details),
        "uncertain_cases_with_warnings": sum(item["expected_uncertainty"] and item["uncertainty_warning_present"] for item in details),
        "human_review_required_cases": sum(item["human_review_required"] for item in details),
    }


def write_visual_evaluation_outputs(evaluation: Mapping[str, Any], output_directory: str | Path) -> tuple[Path, Path]:
    """Write dedicated evaluation JSON and Markdown; source cases remain untouched."""

    root = Path(output_directory).resolve()
    root.mkdir(parents=True, exist_ok=True)
    json_path = root / "evaluation-results.json"
    markdown_path = root / "evaluation-report.md"
    json_path.write_text(json.dumps(evaluation, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    lines = ["# Visual Understanding Model Evaluation", "", f"- Provider: {evaluation['provider_id']}", f"- Model: {evaluation['model_id'] or 'Not reported'}", "", "## Aggregate observations", ""]
    for key, value in evaluation["aggregate"].items():
        lines.append(f"- {key.replace('_', ' ').title()}: {value}")
    lines.extend(["", "No combined accuracy or calibrated confidence score is produced.", "", "## Performance observations", "", f"- Runtime startup: {evaluation['performance']['startup_seconds']:.6f} seconds", f"- Total evaluation: {evaluation['performance']['total_evaluation_seconds']:.6f} seconds", "", "Development measurements are local observations, not published hardware-performance claims.", "", "## Per-case review", ""])
    for item in evaluation["cases"]:
        required_facts = "; ".join(
            f"{value['subject']} {value['relation']} {value['object']}"
            for value in item["expected"]["required_relationships"]
        ) or "(none)"
        warning_text = "; ".join(
            f"{warning['code']}: {warning['message']}" for warning in item["model_result"]["warnings"]
        ) or "(none)"
        lines.extend([
            f"### {item['case_id']}", "", f"- Category: {item['category']}",
            f"- Source image: `{item['source_image']}`", f"- OCR context: {item['ocr_context'] or '(none)'}",
            f"- Structured response: {'Yes' if item['structured_success'] else 'No'}",
            f"- Content type match: {'Yes' if item['content_type_match'] else 'No'}",
            f"- Required relationships missed: {len(item['required_relationships_missed'])}",
            f"- Unsupported relationships: {len(item['unsupported_relationships'])}",
            f"- Prohibited claims detected: {len(item['prohibited_claims_detected'])}",
            f"- Human review required: {'Yes' if item['human_review_required'] else 'No'}",
            f"- Required facts: {required_facts}",
            f"- Required key details: `{json.dumps(item['expected']['required_details'], ensure_ascii=False)}`",
            f"- Prohibited claims: {', '.join(item['expected']['prohibited_claims']) or '(none)'}",
            f"- Model warnings: {warning_text}", "",
            "#### Automatic checks", "",
            f"- Missing required details: {len(item['required_details_missing'])}",
            f"- Expected uncertainty warning present: {'Yes' if item['uncertainty_warning_present'] else 'No'}", "",
            "#### Model result", "", item['model_result']['description'] or item['model_result']['error'] or "(none)", "",
        ])
    markdown_path.write_text("\n".join(lines), encoding="utf-8")
    return json_path, markdown_path
