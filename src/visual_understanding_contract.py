"""Provider-neutral immutable contracts for derived visual understanding."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
import hashlib
import math
import re
from types import MappingProxyType
from typing import Any, Mapping, Protocol, runtime_checkable


_IDENTIFIER = re.compile(r"^[a-z0-9][a-z0-9._-]*$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_LANGUAGE_IDENTIFIER = re.compile(r"^[A-Za-z]{2,3}(?:-[A-Za-z0-9]{2,8})*$")


def _required_text(value: object, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} is required.")
    return value


def _identifier(value: object, name: str) -> str:
    value = _required_text(value, name)
    if not _IDENTIFIER.fullmatch(value):
        raise ValueError(f"{name} must be a stable lowercase identifier.")
    return value


def _finite_number(value: object, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError(f"{name} must be a finite number.")
    return float(value)


def freeze_json_value(value: Any, path: str = "value") -> Any:
    """Validate and recursively freeze one strictly JSON-compatible value."""

    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError(f"{path} cannot contain a non-finite number.")
        return value
    if isinstance(value, (list, tuple)):
        return tuple(freeze_json_value(item, f"{path}[{index}]") for index, item in enumerate(value))
    if isinstance(value, Mapping):
        frozen: dict[str, Any] = {}
        for key, item in value.items():
            if not isinstance(key, str):
                raise ValueError(f"{path} object keys must be strings.")
            frozen[key] = freeze_json_value(item, f"{path}.{key}")
        return MappingProxyType(frozen)
    raise ValueError(f"{path} contains a non-JSON-compatible value: {type(value).__name__}.")


def to_json_compatible(value: Any) -> Any:
    """Return mutable JSON containers from a value accepted by ``freeze_json_value``."""

    if value is None or isinstance(value, (str, bool, int, float)):
        return value
    if isinstance(value, (list, tuple)):
        return [to_json_compatible(item) for item in value]
    if isinstance(value, Mapping):
        return {key: to_json_compatible(item) for key, item in value.items()}
    raise ValueError(f"Value is not a frozen JSON-compatible structure: {type(value).__name__}.")


class VisualContentType(Enum):
    """Small first-release taxonomy for visual information beyond flattened OCR."""

    TEXT_ONLY = "text_only"
    CHART_OR_GRAPH = "chart_or_graph"
    DIAGRAM_OR_PROCESS = "diagram_or_process"
    TABLE = "table"
    MEANINGFUL_FIGURE_OR_PHOTO = "meaningful_figure_or_photo"
    DECORATIVE_OR_BACKGROUND = "decorative_or_background"
    MIXED_OR_UNCERTAIN = "mixed_or_uncertain"


class VisualAnalysisStatus(Enum):
    """Outcome of one provider-boundary visual analysis attempt."""

    SUCCESS = "success"
    FAILURE = "failure"


@dataclass(frozen=True)
class VisualEvidenceReference:
    """Exact immutable source-frame provenance for one derived interpretation."""

    source_reference: str
    checkpoint_path: str | None
    slide_number: int
    build_index: int | None
    frame_number: int
    timestamp: float
    image_width: int
    image_height: int
    authoritative_image_sha256: str
    submitted_image_sha256: str | None = None
    submitted_image_width: int | None = None
    submitted_image_height: int | None = None
    image_transport_revision: str | None = None

    def __post_init__(self) -> None:
        _required_text(self.source_reference, "source_reference")
        if self.checkpoint_path is not None:
            _required_text(self.checkpoint_path, "checkpoint_path")
        if not isinstance(self.slide_number, int) or isinstance(self.slide_number, bool) or self.slide_number < 1:
            raise ValueError("slide_number must be a positive integer.")
        if self.build_index is not None and (
            not isinstance(self.build_index, int) or isinstance(self.build_index, bool) or self.build_index < 0
        ):
            raise ValueError("build_index must be a non-negative integer when supplied.")
        if not isinstance(self.frame_number, int) or isinstance(self.frame_number, bool) or self.frame_number < 0:
            raise ValueError("frame_number must be a non-negative integer.")
        if _finite_number(self.timestamp, "timestamp") < 0:
            raise ValueError("timestamp must not be negative.")
        for value, name in ((self.image_width, "image_width"), (self.image_height, "image_height")):
            if not isinstance(value, int) or isinstance(value, bool) or value < 1:
                raise ValueError(f"{name} must be a positive integer.")
        if not isinstance(self.authoritative_image_sha256, str) or not _SHA256.fullmatch(self.authoritative_image_sha256):
            raise ValueError("authoritative_image_sha256 must be a lowercase SHA-256 digest.")
        if self.submitted_image_sha256 is not None and (
            not isinstance(self.submitted_image_sha256, str)
            or not _SHA256.fullmatch(self.submitted_image_sha256)
        ):
            raise ValueError("submitted_image_sha256 must be a lowercase SHA-256 digest when supplied.")
        submitted_dimensions = (self.submitted_image_width, self.submitted_image_height)
        if any(value is not None for value in submitted_dimensions):
            if any(
                not isinstance(value, int) or isinstance(value, bool) or value < 1
                for value in submitted_dimensions
            ):
                raise ValueError("Submitted image dimensions must both be positive integers when supplied.")
        if self.image_transport_revision is not None:
            _required_text(self.image_transport_revision, "image_transport_revision")
        derivative_recorded = self.submitted_image_sha256 not in (
            None, self.authoritative_image_sha256,
        )
        if derivative_recorded and (
            self.submitted_image_width is None
            or self.submitted_image_height is None
            or self.image_transport_revision is None
        ):
            raise ValueError("A submitted derivative requires dimensions and an image transport revision.")


@dataclass(frozen=True)
class VisualOCRRegion:
    """Small immutable OCR observation supplied as context, never source mutation."""

    source_index: int
    text: str
    confidence: float
    bounding_box: tuple[float, float, float, float]

    def __post_init__(self) -> None:
        if not isinstance(self.source_index, int) or isinstance(self.source_index, bool) or self.source_index < 0:
            raise ValueError("source_index must be a non-negative integer.")
        if not isinstance(self.text, str):
            raise ValueError("text must be a string.")
        confidence = _finite_number(self.confidence, "confidence")
        if not 0 <= confidence <= 1:
            raise ValueError("confidence must be between zero and one.")
        if not isinstance(self.bounding_box, tuple) or len(self.bounding_box) != 4:
            raise ValueError("bounding_box must contain four coordinates.")
        coordinates = tuple(
            _finite_number(value, f"bounding_box[{index}]")
            for index, value in enumerate(self.bounding_box)
        )
        left, top, right, bottom = coordinates
        if left > right or top > bottom:
            raise ValueError("bounding_box must use left, top, right, bottom order.")
        object.__setattr__(self, "confidence", confidence)
        object.__setattr__(self, "bounding_box", coordinates)


@dataclass(frozen=True)
class VisualDetectionSignal:
    """Explicit deterministic observation; it is not calibrated confidence."""

    code: str
    explanation: str
    observed_values: Mapping[str, Any] = field(default_factory=dict)
    detector_revision: str = "visual-detection-v1"

    def __post_init__(self) -> None:
        _identifier(self.code, "code")
        _required_text(self.explanation, "explanation")
        _required_text(self.detector_revision, "detector_revision")
        frozen = freeze_json_value(self.observed_values, "observed_values")
        if not isinstance(frozen, Mapping):
            raise ValueError("observed_values must be a JSON object.")
        object.__setattr__(self, "observed_values", frozen)


@dataclass(frozen=True)
class VisualAnalysisRequest:
    """One exact immutable image/evidence unit submitted for interpretation."""

    request_id: str
    evidence: VisualEvidenceReference
    image_bytes: bytes
    image_media_type: str
    ocr_text: str
    ocr_regions: tuple[VisualOCRRegion, ...] = ()
    detection_signals: tuple[VisualDetectionSignal, ...] = ()
    prompt_schema_revision: str = "visual-understanding-v1"
    interpretation_language: str | None = None

    def __post_init__(self) -> None:
        _required_text(self.request_id, "request_id")
        if not isinstance(self.evidence, VisualEvidenceReference):
            raise ValueError("evidence must be a VisualEvidenceReference.")
        if not isinstance(self.image_bytes, bytes) or not self.image_bytes:
            raise ValueError("image_bytes must contain immutable encoded image data.")
        if self.image_media_type != "image/png":
            raise ValueError("image_media_type must be image/png for canonical frame evidence.")
        if not isinstance(self.ocr_text, str):
            raise ValueError("ocr_text must be a string.")
        if not isinstance(self.ocr_regions, tuple) or any(
            not isinstance(region, VisualOCRRegion) for region in self.ocr_regions
        ):
            raise ValueError("ocr_regions must be a tuple of VisualOCRRegion values.")
        if not isinstance(self.detection_signals, tuple) or any(
            not isinstance(signal, VisualDetectionSignal) for signal in self.detection_signals
        ):
            raise ValueError("detection_signals must be a tuple of VisualDetectionSignal values.")
        _required_text(self.prompt_schema_revision, "prompt_schema_revision")
        if self.interpretation_language is not None and (
            not isinstance(self.interpretation_language, str)
            or not _LANGUAGE_IDENTIFIER.fullmatch(self.interpretation_language)
        ):
            raise ValueError("interpretation_language must be a language identifier when supplied.")
        submitted_hash = hashlib.sha256(self.image_bytes).hexdigest()
        expected_hash = self.evidence.submitted_image_sha256 or self.evidence.authoritative_image_sha256
        if submitted_hash != expected_hash:
            raise ValueError("image_bytes do not match the submitted evidence SHA-256.")


@dataclass(frozen=True)
class VisualRelationship:
    """One simple AI-derived relationship, not a universal semantic graph."""

    subject: str
    relation: str
    object: str

    def __post_init__(self) -> None:
        _required_text(self.subject, "subject")
        _required_text(self.relation, "relation")
        _required_text(self.object, "object")


@dataclass(frozen=True)
class VisualAnalysisWarning:
    """Explicit limitation or ambiguity warning without a confidence score."""

    code: str
    message: str
    details: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        _identifier(self.code, "code")
        _required_text(self.message, "message")
        frozen = freeze_json_value(self.details, "warning.details")
        if not isinstance(frozen, Mapping):
            raise ValueError("warning details must be a JSON object.")
        object.__setattr__(self, "details", frozen)


@dataclass(frozen=True)
class VisualUnderstandingResult:
    """Provider outcome that retains its exact request and source provenance."""

    request: VisualAnalysisRequest
    status: VisualAnalysisStatus
    provider_id: str | None
    model_id: str | None = None
    content_type: VisualContentType | None = None
    description: str | None = None
    relationships: tuple[VisualRelationship, ...] = ()
    structured_details: Mapping[str, Any] = field(default_factory=dict)
    warnings: tuple[VisualAnalysisWarning, ...] = ()
    error: str | None = None
    provider_metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not isinstance(self.request, VisualAnalysisRequest):
            raise ValueError("request must be a VisualAnalysisRequest.")
        if not isinstance(self.status, VisualAnalysisStatus):
            raise ValueError("status must be a VisualAnalysisStatus.")
        if self.provider_id is not None:
            _required_text(self.provider_id, "provider_id")
        if self.model_id is not None:
            _required_text(self.model_id, "model_id")
        if not isinstance(self.relationships, tuple) or any(
            not isinstance(item, VisualRelationship) for item in self.relationships
        ):
            raise ValueError("relationships must be a tuple of VisualRelationship values.")
        if not isinstance(self.warnings, tuple) or any(
            not isinstance(item, VisualAnalysisWarning) for item in self.warnings
        ):
            raise ValueError("warnings must be a tuple of VisualAnalysisWarning values.")
        details = freeze_json_value(self.structured_details, "structured_details")
        metadata = freeze_json_value(self.provider_metadata, "provider_metadata")
        if not isinstance(details, Mapping) or not isinstance(metadata, Mapping):
            raise ValueError("structured_details and provider_metadata must be JSON objects.")
        object.__setattr__(self, "structured_details", details)
        object.__setattr__(self, "provider_metadata", metadata)

        if self.status is VisualAnalysisStatus.SUCCESS:
            if not self.provider_id or not self.model_id:
                raise ValueError("Successful visual analysis requires provider_id and model_id.")
            if not isinstance(self.content_type, VisualContentType):
                raise ValueError("Successful visual analysis requires content_type.")
            _required_text(self.description, "description")
            if self.error is not None:
                raise ValueError("Successful visual analysis cannot include an error.")
        else:
            _required_text(self.error, "error")
            if self.content_type is not None or self.description is not None or self.relationships or self.structured_details:
                raise ValueError("Failed visual analysis cannot contain fabricated interpretation.")

    @property
    def request_id(self) -> str:
        return self.request.request_id

    @property
    def evidence(self) -> VisualEvidenceReference:
        return self.request.evidence


@runtime_checkable
class VisualUnderstandingProvider(Protocol):
    """Minimal provider-neutral boundary for future cloud or local adapters."""

    @property
    def provider_id(self) -> str:
        """Return a stable provider identifier."""

    def analyze(self, request: VisualAnalysisRequest) -> VisualUnderstandingResult:
        """Analyze one exact frame and return an explicit provider outcome."""
