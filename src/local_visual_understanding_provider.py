"""Local llama.cpp visual-understanding provider with strict structured parsing."""

from __future__ import annotations

import base64
from enum import Enum
import json
from types import MappingProxyType
from typing import Any, Mapping

from local_visual_runtime import (
    LocalVisualRuntime,
    LocalVisualRuntimeError,
    LocalVisualRuntimeFailure,
    LocalVisualRuntimeState,
)
from visual_understanding_contract import (
    VisualAnalysisRequest,
    VisualAnalysisStatus,
    VisualAnalysisWarning,
    VisualContentType,
    VisualRelationship,
    VisualUnderstandingResult,
    freeze_json_value,
)


LOCAL_VISUAL_PROVIDER_ID = "local-llama-cpp"
CHAT_COMPLETIONS_ENDPOINT = "/v1/chat/completions"
MAXIMUM_OCR_TEXT_CHARACTERS = 12_000
MAXIMUM_OCR_REGIONS = 50
MAXIMUM_OCR_REGION_TEXT_CHARACTERS = 500
MAXIMUM_RESPONSE_BYTES = 4 * 1024 * 1024


class LocalVisualProviderFailure(str, Enum):
    RUNTIME_NOT_READY = "runtime_not_ready"
    REQUEST_TIMEOUT = "request_timeout"
    LOCAL_RUNTIME_ERROR = "local_runtime_error"
    AUTHENTICATION_FAILED = "authentication_failed"
    MALFORMED_RESPONSE = "malformed_response"
    INVALID_STRUCTURED_OUTPUT = "invalid_structured_output"
    UNSUPPORTED_PROMPT_SCHEMA = "unsupported_prompt_schema"
    UNSUPPORTED_MEDIA_TYPE = "unsupported_media_type"
    MODEL_REFUSAL = "model_refusal"


class LocalVisualStructuredOutputError(ValueError):
    """Raised when one model response violates the exact VideoText schema."""


def _bounded_text(value: str, maximum: int) -> tuple[str, bool]:
    return (value, False) if len(value) <= maximum else (value[:maximum], True)


def build_local_visual_prompt(request: VisualAnalysisRequest) -> str:
    """Build the single authoritative bounded prompt from unchanged request evidence."""

    if not isinstance(request, VisualAnalysisRequest):
        raise ValueError("request must be a VisualAnalysisRequest.")
    ocr_text, ocr_truncated = _bounded_text(request.ocr_text, MAXIMUM_OCR_TEXT_CHARACTERS)
    regions = []
    for region in request.ocr_regions[:MAXIMUM_OCR_REGIONS]:
        region_text, truncated = _bounded_text(region.text, MAXIMUM_OCR_REGION_TEXT_CHARACTERS)
        regions.append({
            "source_index": region.source_index,
            "text": region_text,
            "text_truncated": truncated,
            "confidence": region.confidence,
            "bounding_box": list(region.bounding_box),
        })
    evidence = {
        "ocr_text": ocr_text,
        "ocr_text_truncated": ocr_truncated,
        "ocr_regions": regions,
        "ocr_regions_total": len(request.ocr_regions),
        "ocr_regions_included": len(regions),
    }
    taxonomy = [item.value for item in VisualContentType]
    schema = {
        "content_type": "one exact taxonomy value",
        "description": "non-empty concise string",
        "relationships": [{"subject": "string", "relation": "string", "object": "string"}],
        "structured_details": {},
        "warnings": [{"code": "stable_lowercase_identifier", "message": "string", "details": {}}],
    }
    language = request.interpretation_language or "not specified"
    return "\n".join((
        "Analyze only the supplied source frame for VideoText visual understanding.",
        "The OCR context below is preserved evidence and may contain errors. Do not rewrite or correct OCR.",
        "Describe visual information not safely represented by flattened OCR, and report ambiguity rather than inventing relationships.",
        "Do not produce accessibility certification, approved alt text, translation, OCR correction, confidence percentages, or a lecture summary.",
        f"Interpretation language: {language}",
        f"Prompt/schema revision: {request.prompt_schema_revision}",
        "Allowed content_type values: " + json.dumps(taxonomy, ensure_ascii=False),
        "Return exactly one JSON object, with no Markdown fences and no prose before or after it, matching this schema:",
        json.dumps(schema, ensure_ascii=False, separators=(",", ":")),
        "All five top-level keys are mandatory; never omit a key.",
        "Use [] when there are no relationships or warnings, and use {} when there are no structured_details.",
        "Only include warnings for genuine visual ambiguity or limitations; do not invent a warning to fill the array.",
        "OCR evidence (verbatim within the documented deterministic bounds):",
        json.dumps(evidence, ensure_ascii=False, separators=(",", ":")),
    ))


def build_llama_visual_request(request: VisualAnalysisRequest, model_id: str) -> dict[str, Any]:
    """Build the isolated fake/llama.cpp-compatible multimodal transport envelope."""

    prompt = build_local_visual_prompt(request)
    image_data = base64.b64encode(request.image_bytes).decode("ascii")
    return {
        "model": model_id,
        "messages": [{
            "role": "user",
            "content": [
                {"type": "text", "text": prompt},
                {"type": "image_url", "image_url": {
                    "url": f"data:{request.image_media_type};base64,{image_data}"
                }},
            ],
        }],
        "temperature": 0,
        "stream": False,
        "response_format": {"type": "json_object"},
    }


def _unique_object(pairs):
    value = {}
    for key, item in pairs:
        if key in value:
            raise LocalVisualStructuredOutputError(f"Duplicate JSON field: {key}.")
        value[key] = item
    return value


def _reject_constant(value: str):
    raise LocalVisualStructuredOutputError(f"Unsupported JSON numeric value: {value}.")


def _exact_fields(value: Mapping[str, Any], expected: set[str], path: str) -> None:
    actual = set(value)
    missing = expected - actual
    extra = actual - expected
    if missing:
        raise LocalVisualStructuredOutputError(f"{path} is missing required fields: {', '.join(sorted(missing))}.")
    if extra:
        raise LocalVisualStructuredOutputError(f"{path} contains unsupported fields: {', '.join(sorted(extra))}.")


def parse_local_visual_structured_output(
    raw_output: str,
    request: VisualAnalysisRequest,
    *,
    provider_id: str,
    model_id: str,
    provider_metadata: Mapping[str, Any],
) -> VisualUnderstandingResult:
    """Parse exactly one JSON object and validate every approved 1.8 field."""

    if not isinstance(raw_output, str) or not raw_output.strip():
        raise LocalVisualStructuredOutputError("Model output must be one non-empty JSON object.")
    try:
        value = json.loads(
            raw_output,
            object_pairs_hook=_unique_object,
            parse_constant=_reject_constant,
        )
    except LocalVisualStructuredOutputError:
        raise
    except json.JSONDecodeError as error:
        raise LocalVisualStructuredOutputError("Model output is not exactly one valid JSON object.") from error
    if not isinstance(value, dict):
        raise LocalVisualStructuredOutputError("Model output must be a JSON object.")
    _exact_fields(value, {"content_type", "description", "relationships", "structured_details", "warnings"}, "result")
    try:
        content_type = VisualContentType(value["content_type"])
    except (TypeError, ValueError) as error:
        raise LocalVisualStructuredOutputError("content_type is not an approved visual taxonomy value.") from error
    description = value["description"]
    if not isinstance(description, str) or not description.strip():
        raise LocalVisualStructuredOutputError("description must be a non-empty string.")
    relationship_values = value["relationships"]
    if not isinstance(relationship_values, list):
        raise LocalVisualStructuredOutputError("relationships must be a JSON array.")
    relationships = []
    for index, item in enumerate(relationship_values):
        if not isinstance(item, dict):
            raise LocalVisualStructuredOutputError(f"relationships[{index}] must be a JSON object.")
        _exact_fields(item, {"subject", "relation", "object"}, f"relationships[{index}]")
        if any(not isinstance(item[field], str) or not item[field].strip()
               for field in ("subject", "relation", "object")):
            raise LocalVisualStructuredOutputError(
                f"relationships[{index}] fields must be non-empty strings."
            )
        relationships.append(VisualRelationship(item["subject"], item["relation"], item["object"]))
    structured_details = value["structured_details"]
    if not isinstance(structured_details, dict):
        raise LocalVisualStructuredOutputError("structured_details must be a JSON object.")
    warning_values = value["warnings"]
    if not isinstance(warning_values, list):
        raise LocalVisualStructuredOutputError("warnings must be a JSON array.")
    warnings = []
    for index, item in enumerate(warning_values):
        if not isinstance(item, dict):
            raise LocalVisualStructuredOutputError(f"warnings[{index}] must be a JSON object.")
        _exact_fields(item, {"code", "message", "details"}, f"warnings[{index}]")
        if not isinstance(item["code"], str) or not isinstance(item["message"], str):
            raise LocalVisualStructuredOutputError(f"warnings[{index}] code and message must be strings.")
        if not isinstance(item["details"], dict):
            raise LocalVisualStructuredOutputError(f"warnings[{index}].details must be a JSON object.")
        try:
            warnings.append(VisualAnalysisWarning(item["code"], item["message"], item["details"]))
        except ValueError as error:
            raise LocalVisualStructuredOutputError(f"warnings[{index}] is invalid.") from error
    try:
        frozen_details = freeze_json_value(structured_details, "structured_details")
        return VisualUnderstandingResult(
            request=request,
            status=VisualAnalysisStatus.SUCCESS,
            provider_id=provider_id,
            model_id=model_id,
            content_type=content_type,
            description=description,
            relationships=tuple(relationships),
            structured_details=frozen_details,
            warnings=tuple(warnings),
            provider_metadata=provider_metadata,
        )
    except ValueError as error:
        raise LocalVisualStructuredOutputError("Structured model output failed contract validation.") from error


def _declared_hash(runtime: LocalVisualRuntime, resolved_path) -> str:
    matches = tuple(item.sha256 for item in runtime.pack.declared_files if item.resolved_path == resolved_path)
    if len(matches) != 1:
        raise ValueError("Verified pack does not retain one model file declaration.")
    return matches[0]


class LocalVisualUnderstandingProvider:
    """Existing-contract adapter for one already-ready authenticated local runtime."""

    provider_id = LOCAL_VISUAL_PROVIDER_ID

    def __init__(self, runtime: LocalVisualRuntime, *, request_timeout: float = 150.0) -> None:
        if not isinstance(runtime, LocalVisualRuntime):
            raise ValueError("runtime must be a LocalVisualRuntime.")
        if isinstance(request_timeout, bool) or not isinstance(request_timeout, (int, float)) or request_timeout <= 0:
            raise ValueError("request_timeout must be a positive number.")
        self._runtime = runtime
        self._request_timeout = float(request_timeout)
        self._metadata = MappingProxyType({
            "pack_id": runtime.pack.pack_id,
            "pack_version": runtime.pack.pack_version,
            "runtime_family": runtime.pack.runtime_family,
            "runtime_version": runtime.pack.runtime_version,
            "runtime_backend": runtime.pack.runtime_backend,
            "model_family": runtime.pack.model_family,
            "model_revision": runtime.pack.model_revision,
            "model_sha256": _declared_hash(runtime, runtime.pack.model_file),
            "projector_sha256": _declared_hash(runtime, runtime.pack.projector_file),
            "network_required": runtime.pack.network_required,
        })

    def _failure(
        self,
        request: VisualAnalysisRequest,
        category: LocalVisualProviderFailure,
        message: str,
    ) -> VisualUnderstandingResult:
        metadata = dict(self._metadata)
        metadata["prompt_schema_revision"] = request.prompt_schema_revision
        return VisualUnderstandingResult(
            request=request,
            status=VisualAnalysisStatus.FAILURE,
            provider_id=self.provider_id,
            model_id=self._runtime.pack.model_id,
            error=f"{category.value}: {message}",
            provider_metadata=metadata,
        )

    def analyze(self, request: VisualAnalysisRequest) -> VisualUnderstandingResult:
        """Submit one exact canonical PNG once and strictly parse its local result."""

        if not isinstance(request, VisualAnalysisRequest):
            raise ValueError("request must be a VisualAnalysisRequest.")
        if self._runtime.state is not LocalVisualRuntimeState.READY:
            return self._failure(
                request, LocalVisualProviderFailure.RUNTIME_NOT_READY,
                "The local visual-understanding runtime is not ready.",
            )
        if not self._runtime.pack.supports_prompt_schema(request.prompt_schema_revision):
            return self._failure(
                request, LocalVisualProviderFailure.UNSUPPORTED_PROMPT_SCHEMA,
                "The installed local visual pack does not support this prompt/schema revision.",
            )
        if request.image_media_type not in self._runtime.pack.supported_image_media_types:
            return self._failure(
                request, LocalVisualProviderFailure.UNSUPPORTED_MEDIA_TYPE,
                "The installed local visual pack does not support this image media type.",
            )
        transport = build_llama_visual_request(request, self._runtime.pack.model_id)
        try:
            envelope = self._runtime.post_json(
                CHAT_COMPLETIONS_ENDPOINT,
                transport,
                timeout=self._request_timeout,
                maximum_response_bytes=MAXIMUM_RESPONSE_BYTES,
            )
        except LocalVisualRuntimeError as error:
            category = {
                LocalVisualRuntimeFailure.REQUEST_TIMEOUT: LocalVisualProviderFailure.REQUEST_TIMEOUT,
                LocalVisualRuntimeFailure.AUTHENTICATION_FAILED: LocalVisualProviderFailure.AUTHENTICATION_FAILED,
                LocalVisualRuntimeFailure.RUNTIME_UNAVAILABLE: LocalVisualProviderFailure.RUNTIME_NOT_READY,
            }.get(error.category, LocalVisualProviderFailure.LOCAL_RUNTIME_ERROR)
            return self._failure(request, category, "The local visual-understanding request failed safely.")
        try:
            choices = envelope.get("choices")
            if not isinstance(choices, list) or len(choices) != 1 or not isinstance(choices[0], dict):
                raise LocalVisualStructuredOutputError("Runtime response must contain exactly one choice.")
            message = choices[0].get("message")
            if not isinstance(message, dict):
                raise LocalVisualStructuredOutputError("Runtime response choice must contain one message.")
            refusal = message.get("refusal")
            if isinstance(refusal, str) and refusal.strip():
                return self._failure(
                    request, LocalVisualProviderFailure.MODEL_REFUSAL,
                    "The local visual model declined to interpret this frame.",
                )
            content = message.get("content")
            if not isinstance(content, str):
                raise LocalVisualStructuredOutputError("Runtime response message content must be a string.")
        except LocalVisualStructuredOutputError:
            return self._failure(
                request, LocalVisualProviderFailure.MALFORMED_RESPONSE,
                "The local visual runtime returned a malformed response envelope.",
            )
        metadata = dict(self._metadata)
        metadata["prompt_schema_revision"] = request.prompt_schema_revision
        try:
            return parse_local_visual_structured_output(
                content,
                request,
                provider_id=self.provider_id,
                model_id=self._runtime.pack.model_id,
                provider_metadata=metadata,
            )
        except LocalVisualStructuredOutputError as error:
            category = (
                LocalVisualProviderFailure.MALFORMED_RESPONSE
                if "valid JSON object" in str(error) else LocalVisualProviderFailure.INVALID_STRUCTURED_OUTPUT
            )
            return self._failure(
                request, category,
                "The local visual model returned output that did not match the required schema.",
            )
