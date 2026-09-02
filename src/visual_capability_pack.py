"""Manifest-only discovery for optional local visual-understanding packs."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from hashlib import sha256
import json
import os
from pathlib import Path
import re
from typing import Mapping, Sequence

from app_info import APP_RELEASE


CAPABILITY_PACK_SCHEMA = "videotext.capability_pack"
CAPABILITY_PACK_SCHEMA_VERSION = "1.0"
VISUAL_CAPABILITY = "visual_understanding"
VISUAL_PACK_MANIFEST_FILENAME = "videotext-capability-pack.json"
VISUAL_PACK_ROOT_ENVIRONMENT_VARIABLE = "VIDEOTEXT_VISION_MODELS"
CURRENT_VISUAL_PROMPT_SCHEMA_REVISION = "visual-understanding-v1"

_IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_VERSION = re.compile(r"^(\d+)(?:\.(\d+))?(?:\.(\d+))?(?:\.(\d+))?(?:-[A-Za-z0-9][A-Za-z0-9.-]*)?$")


class VisualCapabilityPackError(ValueError):
    """Raised when a local visual capability-pack manifest is unsafe or invalid."""


class VisualPackReadinessState(str, Enum):
    """Overall request-specific readiness without a confidence score."""

    READY = "ready"
    PARTIAL = "partial"
    NOT_READY = "not_ready"


class VisualPackIntegrityState(str, Enum):
    """Local file-integrity state at the selected verification level."""

    VERIFIED = "verified"
    UNVERIFIED = "unverified"
    MISSING = "missing"
    INVALID = "invalid"


class VisualPackBackendState(str, Enum):
    """Static backend result; GPU execution is confirmed only at runtime start."""

    STRUCTURALLY_READY = "structurally_ready"
    RUNTIME_UNCONFIRMED = "runtime_unconfirmed"
    UNSUPPORTED = "unsupported"


class VisualPackReadinessCategory(str, Enum):
    """Stable, safe readiness issue categories for later GUI/provider use."""

    INCOMPATIBLE_APP_VERSION = "incompatible_app_version"
    UNSUPPORTED_PROMPT_SCHEMA = "unsupported_prompt_schema"
    UNSUPPORTED_MEDIA_TYPE = "unsupported_media_type"
    MISSING_FILE = "missing_file"
    HASH_MISMATCH = "hash_mismatch"
    UNSAFE_PATH = "unsafe_path"
    INVALID_RUNTIME = "invalid_runtime"
    INVALID_MODEL = "invalid_model"
    INVALID_PROJECTOR = "invalid_projector"
    BACKEND_UNCONFIRMED = "backend_unconfirmed"
    INTEGRITY_UNVERIFIED = "integrity_unverified"
    NETWORK_REQUIRED = "network_required"


def default_visual_pack_root(environ: Mapping[str, str] | None = None) -> Path:
    """Return the no-admin visual-pack root, honoring an explicit portable override."""

    values = os.environ if environ is None else environ
    configured = values.get(VISUAL_PACK_ROOT_ENVIRONMENT_VARIABLE, "").strip()
    if configured:
        return Path(configured).expanduser().resolve()
    local_app_data = values.get("LOCALAPPDATA", "").strip()
    base = Path(local_app_data).expanduser() if local_app_data else Path.home() / "AppData" / "Local"
    return (base / "VideoText" / "models" / "vision").resolve()


def _required_text(value: object, path: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise VisualCapabilityPackError(f"{path} must be a non-empty string.")
    return value


def _identifier(value: object, path: str) -> str:
    text = _required_text(value, path)
    if not _IDENTIFIER.fullmatch(text):
        raise VisualCapabilityPackError(f"{path} must be a stable identifier.")
    return text


def _object(value: object, path: str) -> dict:
    if not isinstance(value, dict):
        raise VisualCapabilityPackError(f"{path} must be a JSON object.")
    return value


def _array(value: object, path: str) -> list:
    if not isinstance(value, list):
        raise VisualCapabilityPackError(f"{path} must be a JSON array.")
    return value


def _required(mapping: Mapping[str, object], fields: tuple[str, ...], path: str) -> None:
    missing = tuple(field for field in fields if field not in mapping)
    if missing:
        raise VisualCapabilityPackError(
            f"{path} is missing required field(s): {', '.join(missing)}."
        )


def _relative_path(value: object, path: str) -> Path:
    text = _required_text(value, path)
    candidate = Path(text)
    if (
        candidate.is_absolute()
        or candidate.drive
        or candidate.root
        or text.startswith(("\\\\", "//"))
        or any(part in ("", ".", "..") for part in candidate.parts)
    ):
        raise VisualCapabilityPackError(f"{path} must be a safe relative path.")
    return candidate


def _inside(pack_root: Path, relative_path: Path, path: str) -> Path:
    root = pack_root.resolve()
    resolved = (root / relative_path).resolve()
    if not resolved.is_relative_to(root):
        raise VisualCapabilityPackError(f"{path} escapes the capability-pack root.")
    return resolved


def _version_tuple(value: object, path: str) -> tuple[int, int, int, int]:
    text = _required_text(value, path)
    match = _VERSION.fullmatch(text)
    if not match:
        raise VisualCapabilityPackError(f"{path} must be a dotted application version.")
    return tuple(int(part or 0) for part in match.groups())


@dataclass(frozen=True)
class VisualPackDeclaredFile:
    """One immutable, safe file declaration without eager content hashing."""

    relative_path: Path
    resolved_path: Path
    sha256: str
    exists: bool


@dataclass(frozen=True)
class VisualCapabilityPackAvailability:
    """Manifest-level availability; this is not executable/model readiness."""

    pack_root: Path
    manifest_path: Path
    pack_id: str
    pack_version: str
    provider_id: str
    runtime_family: str
    runtime_version: str
    runtime_backend: str
    runtime_executable: Path
    model_id: str
    model_family: str
    model_revision: str
    model_file: Path
    projector_file: Path
    model_license: str
    model_source_repository: str
    redistribution_provenance: str
    supported_prompt_schema_revisions: tuple[str, ...]
    supported_image_media_types: tuple[str, ...]
    minimum_videotext_version: str
    network_required: bool
    declared_files: tuple[VisualPackDeclaredFile, ...]
    license_notice_paths: tuple[Path, ...]
    compatible: bool
    errors: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()

    def supports_prompt_schema(self, revision: str) -> bool:
        """Report prompt compatibility without choosing a provider or loading a model."""

        return revision in self.supported_prompt_schema_revisions


@dataclass(frozen=True)
class VisualCapabilityPackDiscoveryIssue:
    """One invalid manifest that did not prevent discovery of other packs."""

    manifest_path: Path
    error: str


@dataclass(frozen=True)
class VisualCapabilityPackDiscovery:
    """Immutable discovery result across one or more explicit roots."""

    searched_roots: tuple[Path, ...]
    packs: tuple[VisualCapabilityPackAvailability, ...]
    issues: tuple[VisualCapabilityPackDiscoveryIssue, ...]


@dataclass(frozen=True)
class VisualPackReadinessIssue:
    """One categorized local preflight finding with safe optional hash evidence."""

    category: VisualPackReadinessCategory
    message: str
    relative_path: Path | None = None
    declared_sha256: str | None = None
    observed_sha256: str | None = None


@dataclass(frozen=True)
class VisualCapabilityPackReadiness:
    """Immutable request-specific pack readiness without starting its runtime."""

    pack_id: str
    pack_version: str
    provider_id: str
    state: VisualPackReadinessState
    requested_prompt_schema: str
    requested_image_media_type: str
    prompt_schema_compatible: bool
    image_media_compatible: bool
    application_version_compatible: bool
    required_files_integrity: VisualPackIntegrityState
    runtime_integrity: VisualPackIntegrityState
    model_integrity: VisualPackIntegrityState
    projector_integrity: VisualPackIntegrityState
    backend_declared: str
    backend_readiness: VisualPackBackendState
    hashes_verified: bool
    warnings: tuple[VisualPackReadinessIssue, ...] = ()
    errors: tuple[VisualPackReadinessIssue, ...] = ()


def _string_tuple(value: object, path: str) -> tuple[str, ...]:
    values = _array(value, path)
    result = tuple(_required_text(item, f"{path}[{index}]") for index, item in enumerate(values))
    if not result:
        raise VisualCapabilityPackError(f"{path} must not be empty.")
    if len(result) != len(set(result)):
        raise VisualCapabilityPackError(f"{path} must not contain duplicates.")
    return result


def load_visual_capability_pack_manifest(
    manifest_path: str | Path,
    *,
    application_version: str = APP_RELEASE,
) -> VisualCapabilityPackAvailability:
    """Validate one manifest and check declared file presence without hashing or execution."""

    path = Path(manifest_path).resolve()
    pack_root = path.parent.resolve()
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise VisualCapabilityPackError(
            f"Capability-pack manifest could not be loaded: {type(error).__name__}: {error}"
        ) from error
    data = _object(document, "manifest")
    _required(data, (
        "schema", "schema_version", "capability", "pack_id", "pack_version",
        "provider_id", "runtime", "model", "supported_prompt_schema_revisions",
        "supported_image_media_types", "minimum_videotext_version", "network_required",
        "files", "license_notice_paths",
    ), "manifest")
    if data["schema"] != CAPABILITY_PACK_SCHEMA:
        raise VisualCapabilityPackError(f"Unsupported capability-pack schema: {data['schema']}.")
    if data["schema_version"] != CAPABILITY_PACK_SCHEMA_VERSION:
        raise VisualCapabilityPackError(
            f"Unsupported capability-pack schema version: {data['schema_version']}."
        )
    if data["capability"] != VISUAL_CAPABILITY:
        raise VisualCapabilityPackError(f"Unsupported capability: {data['capability']}.")

    runtime = _object(data["runtime"], "runtime")
    model = _object(data["model"], "model")
    _required(runtime, ("family", "version", "backend", "executable"), "runtime")
    _required(model, (
        "id", "family", "revision", "model_file", "projector_file", "license",
        "source_repository", "redistribution_provenance",
    ), "model")
    runtime_relative = _relative_path(runtime["executable"], "runtime.executable")
    model_relative = _relative_path(model["model_file"], "model.model_file")
    projector_relative = _relative_path(model["projector_file"], "model.projector_file")

    file_values = _array(data["files"], "files")
    if not file_values:
        raise VisualCapabilityPackError("files must not be empty.")
    declared_files = []
    logical_paths: set[str] = set()
    for index, value in enumerate(file_values):
        file_path = f"files[{index}]"
        item = _object(value, file_path)
        _required(item, ("path", "sha256"), file_path)
        relative = _relative_path(item["path"], f"{file_path}.path")
        logical = relative.as_posix().casefold()
        if logical in logical_paths:
            raise VisualCapabilityPackError(f"Duplicate declared file: {relative.as_posix()}.")
        logical_paths.add(logical)
        digest = _required_text(item["sha256"], f"{file_path}.sha256")
        if not _SHA256.fullmatch(digest):
            raise VisualCapabilityPackError(f"{file_path}.sha256 must be a lowercase SHA-256 digest.")
        resolved = _inside(pack_root, relative, f"{file_path}.path")
        declared_files.append(VisualPackDeclaredFile(relative, resolved, digest, resolved.is_file()))

    principal = (runtime_relative, model_relative, projector_relative)
    missing_declarations = tuple(item.as_posix() for item in principal if item.as_posix().casefold() not in logical_paths)
    if missing_declarations:
        raise VisualCapabilityPackError(
            "Runtime/model/projector files must be declared in files: " + ", ".join(missing_declarations) + "."
        )

    notices = tuple(
        _inside(pack_root, _relative_path(value, f"license_notice_paths[{index}]"),
                f"license_notice_paths[{index}]")
        for index, value in enumerate(_array(data["license_notice_paths"], "license_notice_paths"))
    )
    if not notices:
        raise VisualCapabilityPackError("license_notice_paths must not be empty.")
    if len({str(item).casefold() for item in notices}) != len(notices):
        raise VisualCapabilityPackError("license_notice_paths must not contain duplicates.")

    network_required = data["network_required"]
    if not isinstance(network_required, bool):
        raise VisualCapabilityPackError("network_required must be a boolean.")
    minimum = _required_text(data["minimum_videotext_version"], "minimum_videotext_version")
    minimum_tuple = _version_tuple(minimum, "minimum_videotext_version")
    application_tuple = _version_tuple(application_version, "application_version")
    errors = [f"Declared file is missing: {item.relative_path.as_posix()}."
              for item in declared_files if not item.exists]
    errors.extend(f"License notice is missing: {item.relative_to(pack_root).as_posix()}."
                  for item in notices if not item.is_file())
    if minimum_tuple > application_tuple:
        errors.append(
            f"Pack requires VideoText {minimum} or later; current version is {application_version}."
        )
    if network_required:
        errors.append("Pack declares that network access is required; local offline packs must not require it.")

    return VisualCapabilityPackAvailability(
        pack_root=pack_root,
        manifest_path=path,
        pack_id=_identifier(data["pack_id"], "pack_id"),
        pack_version=_required_text(data["pack_version"], "pack_version"),
        provider_id=_identifier(data["provider_id"], "provider_id"),
        runtime_family=_required_text(runtime["family"], "runtime.family"),
        runtime_version=_required_text(runtime["version"], "runtime.version"),
        runtime_backend=_identifier(runtime["backend"], "runtime.backend"),
        runtime_executable=_inside(pack_root, runtime_relative, "runtime.executable"),
        model_id=_required_text(model["id"], "model.id"),
        model_family=_required_text(model["family"], "model.family"),
        model_revision=_required_text(model["revision"], "model.revision"),
        model_file=_inside(pack_root, model_relative, "model.model_file"),
        projector_file=_inside(pack_root, projector_relative, "model.projector_file"),
        model_license=_required_text(model["license"], "model.license"),
        model_source_repository=_required_text(model["source_repository"], "model.source_repository"),
        redistribution_provenance=_required_text(
            model["redistribution_provenance"], "model.redistribution_provenance"
        ),
        supported_prompt_schema_revisions=_string_tuple(
            data["supported_prompt_schema_revisions"], "supported_prompt_schema_revisions"
        ),
        supported_image_media_types=_string_tuple(
            data["supported_image_media_types"], "supported_image_media_types"
        ),
        minimum_videotext_version=minimum,
        network_required=network_required,
        declared_files=tuple(declared_files),
        license_notice_paths=notices,
        compatible=not errors,
        errors=tuple(errors),
    )


def discover_visual_capability_packs(
    roots: Sequence[str | Path] | None = None,
    *,
    application_version: str = APP_RELEASE,
    environ: Mapping[str, str] | None = None,
) -> VisualCapabilityPackDiscovery:
    """Discover explicit manifests without recursion, execution, hashing, or network access."""

    selected = (default_visual_pack_root(environ),) if roots is None else tuple(Path(root).expanduser().resolve() for root in roots)
    normalized = tuple(dict.fromkeys(path.resolve() for path in selected))
    packs = []
    issues = []
    for root in normalized:
        if not root.is_dir():
            continue
        manifests = sorted(root.glob(f"*/{VISUAL_PACK_MANIFEST_FILENAME}"))
        if (root / VISUAL_PACK_MANIFEST_FILENAME).is_file():
            manifests.insert(0, root / VISUAL_PACK_MANIFEST_FILENAME)
        for manifest in manifests:
            try:
                packs.append(load_visual_capability_pack_manifest(
                    manifest, application_version=application_version
                ))
            except VisualCapabilityPackError as error:
                issues.append(VisualCapabilityPackDiscoveryIssue(manifest.resolve(), str(error)))
    packs.sort(key=lambda item: (item.pack_id, item.pack_version, str(item.pack_root).casefold()))
    issues.sort(key=lambda item: str(item.manifest_path).casefold())
    return VisualCapabilityPackDiscovery(normalized, tuple(packs), tuple(issues))


_HASH_CHUNK_SIZE = 1024 * 1024


def _stream_sha256(path: Path) -> str:
    """Hash a potentially multi-GB local file with bounded memory use."""

    digest = sha256()
    with path.open("rb") as source:
        while chunk := source.read(_HASH_CHUNK_SIZE):
            digest.update(chunk)
    return digest.hexdigest()


def _principal_declaration(
    pack: VisualCapabilityPackAvailability,
    principal_path: Path,
) -> VisualPackDeclaredFile:
    matches = tuple(item for item in pack.declared_files if item.resolved_path == principal_path)
    if len(matches) != 1:
        raise ValueError("Discovered pack does not retain one principal file declaration.")
    return matches[0]


def check_visual_capability_pack_readiness(
    pack: VisualCapabilityPackAvailability,
    *,
    requested_prompt_schema: str,
    requested_image_media_type: str = "image/png",
    verify_hashes: bool = True,
    application_version: str = APP_RELEASE,
) -> VisualCapabilityPackReadiness:
    """Perform local-only file/request preflight without executing or loading a model."""

    if not isinstance(pack, VisualCapabilityPackAvailability):
        raise ValueError("pack must be a VisualCapabilityPackAvailability.")
    prompt = _required_text(requested_prompt_schema, "requested_prompt_schema")
    media = _required_text(requested_image_media_type, "requested_image_media_type")
    if not isinstance(verify_hashes, bool):
        raise ValueError("verify_hashes must be a boolean.")
    errors: list[VisualPackReadinessIssue] = []
    warnings: list[VisualPackReadinessIssue] = []

    prompt_compatible = pack.supports_prompt_schema(prompt)
    if not prompt_compatible:
        errors.append(VisualPackReadinessIssue(
            VisualPackReadinessCategory.UNSUPPORTED_PROMPT_SCHEMA,
            f"Pack does not support prompt/schema revision: {prompt}.",
        ))
    media_compatible = media in pack.supported_image_media_types
    if not media_compatible:
        errors.append(VisualPackReadinessIssue(
            VisualPackReadinessCategory.UNSUPPORTED_MEDIA_TYPE,
            f"Pack does not support image media type: {media}.",
        ))
    application_compatible = (
        _version_tuple(pack.minimum_videotext_version, "minimum_videotext_version")
        <= _version_tuple(application_version, "application_version")
    )
    if not application_compatible:
        errors.append(VisualPackReadinessIssue(
            VisualPackReadinessCategory.INCOMPATIBLE_APP_VERSION,
            f"Pack requires VideoText {pack.minimum_videotext_version} or later; "
            f"current version is {application_version}.",
        ))
    if pack.network_required:
        errors.append(VisualPackReadinessIssue(
            VisualPackReadinessCategory.NETWORK_REQUIRED,
            "Pack declares network access is required and is not ready for local offline analysis.",
        ))

    runtime_declaration = _principal_declaration(pack, pack.runtime_executable)
    model_declaration = _principal_declaration(pack, pack.model_file)
    projector_declaration = _principal_declaration(pack, pack.projector_file)
    principal_categories = {
        runtime_declaration.relative_path.as_posix().casefold(): VisualPackReadinessCategory.INVALID_RUNTIME,
        model_declaration.relative_path.as_posix().casefold(): VisualPackReadinessCategory.INVALID_MODEL,
        projector_declaration.relative_path.as_posix().casefold(): VisualPackReadinessCategory.INVALID_PROJECTOR,
    }
    integrity: dict[str, VisualPackIntegrityState] = {}
    root = pack.pack_root.resolve()
    for declaration in pack.declared_files:
        logical = declaration.relative_path.as_posix().casefold()
        try:
            current_path = (root / declaration.relative_path).resolve()
            if not current_path.is_relative_to(root):
                raise VisualCapabilityPackError("resolved path escapes pack root")
        except (OSError, RuntimeError, VisualCapabilityPackError):
            integrity[logical] = VisualPackIntegrityState.INVALID
            errors.append(VisualPackReadinessIssue(
                VisualPackReadinessCategory.UNSAFE_PATH,
                f"Declared file no longer resolves safely inside the pack: {declaration.relative_path.as_posix()}.",
                declaration.relative_path,
            ))
            continue
        if not current_path.is_file():
            integrity[logical] = VisualPackIntegrityState.MISSING
            errors.append(VisualPackReadinessIssue(
                VisualPackReadinessCategory.MISSING_FILE,
                f"Required pack file is missing: {declaration.relative_path.as_posix()}.",
                declaration.relative_path,
                declaration.sha256,
            ))
            continue
        if verify_hashes:
            try:
                observed = _stream_sha256(current_path)
            except OSError:
                integrity[logical] = VisualPackIntegrityState.INVALID
                errors.append(VisualPackReadinessIssue(
                    principal_categories.get(logical, VisualPackReadinessCategory.MISSING_FILE),
                    f"Required pack file could not be read: {declaration.relative_path.as_posix()}.",
                    declaration.relative_path,
                    declaration.sha256,
                ))
                continue
            if observed != declaration.sha256:
                integrity[logical] = VisualPackIntegrityState.INVALID
                errors.append(VisualPackReadinessIssue(
                    VisualPackReadinessCategory.HASH_MISMATCH,
                    f"SHA-256 mismatch for required pack file: {declaration.relative_path.as_posix()}.",
                    declaration.relative_path,
                    declaration.sha256,
                    observed,
                ))
            else:
                integrity[logical] = VisualPackIntegrityState.VERIFIED
        else:
            integrity[logical] = VisualPackIntegrityState.UNVERIFIED

    def principal_state(declaration: VisualPackDeclaredFile) -> VisualPackIntegrityState:
        return integrity[declaration.relative_path.as_posix().casefold()]

    runtime_state = principal_state(runtime_declaration)
    model_state = principal_state(model_declaration)
    projector_state = principal_state(projector_declaration)
    if runtime_state not in (VisualPackIntegrityState.MISSING, VisualPackIntegrityState.INVALID):
        if pack.runtime_executable.suffix.casefold() != ".exe":
            runtime_state = VisualPackIntegrityState.INVALID
            errors.append(VisualPackReadinessIssue(
                VisualPackReadinessCategory.INVALID_RUNTIME,
                "Runtime executable must be a Windows .exe file.",
                runtime_declaration.relative_path,
            ))
    if model_state not in (VisualPackIntegrityState.MISSING, VisualPackIntegrityState.INVALID):
        if pack.model_file.suffix.casefold() != ".gguf":
            model_state = VisualPackIntegrityState.INVALID
            errors.append(VisualPackReadinessIssue(
                VisualPackReadinessCategory.INVALID_MODEL,
                "Model file must use the declared GGUF format.",
                model_declaration.relative_path,
            ))
    if projector_state not in (VisualPackIntegrityState.MISSING, VisualPackIntegrityState.INVALID):
        if pack.projector_file.suffix.casefold() != ".gguf":
            projector_state = VisualPackIntegrityState.INVALID
            errors.append(VisualPackReadinessIssue(
                VisualPackReadinessCategory.INVALID_PROJECTOR,
                "Projector file must use the declared GGUF format.",
                projector_declaration.relative_path,
            ))
    try:
        same_principal = pack.model_file.resolve().samefile(pack.projector_file.resolve())
    except OSError:
        same_principal = pack.model_file.resolve() == pack.projector_file.resolve()
    if same_principal:
        projector_state = VisualPackIntegrityState.INVALID
        errors.append(VisualPackReadinessIssue(
            VisualPackReadinessCategory.INVALID_PROJECTOR,
            "Model and projector must be distinct regular files.",
            projector_declaration.relative_path,
        ))

    states = tuple(integrity.values()) + (runtime_state, model_state, projector_state)
    if any(state is VisualPackIntegrityState.INVALID for state in states):
        required_state = VisualPackIntegrityState.INVALID
    elif any(state is VisualPackIntegrityState.MISSING for state in states):
        required_state = VisualPackIntegrityState.MISSING
    elif verify_hashes:
        required_state = VisualPackIntegrityState.VERIFIED
    else:
        required_state = VisualPackIntegrityState.UNVERIFIED
        warnings.append(VisualPackReadinessIssue(
            VisualPackReadinessCategory.INTEGRITY_UNVERIFIED,
            "Required pack files exist but SHA-256 verification was not requested.",
        ))

    backend = pack.runtime_backend.casefold()
    if backend == "cpu":
        backend_state = VisualPackBackendState.STRUCTURALLY_READY
    elif backend in {"cpu-vulkan", "vulkan", "cuda"}:
        backend_state = VisualPackBackendState.RUNTIME_UNCONFIRMED
        warnings.append(VisualPackReadinessIssue(
            VisualPackReadinessCategory.BACKEND_UNCONFIRMED,
            f"Backend '{pack.runtime_backend}' requires confirmation when the local runtime starts.",
        ))
    else:
        backend_state = VisualPackBackendState.UNSUPPORTED
        errors.append(VisualPackReadinessIssue(
            VisualPackReadinessCategory.INVALID_RUNTIME,
            f"Unsupported declared runtime backend: {pack.runtime_backend}.",
        ))

    state = (
        VisualPackReadinessState.NOT_READY if errors
        else VisualPackReadinessState.PARTIAL if warnings
        else VisualPackReadinessState.READY
    )
    return VisualCapabilityPackReadiness(
        pack_id=pack.pack_id,
        pack_version=pack.pack_version,
        provider_id=pack.provider_id,
        state=state,
        requested_prompt_schema=prompt,
        requested_image_media_type=media,
        prompt_schema_compatible=prompt_compatible,
        image_media_compatible=media_compatible,
        application_version_compatible=application_compatible,
        required_files_integrity=required_state,
        runtime_integrity=runtime_state,
        model_integrity=model_state,
        projector_integrity=projector_state,
        backend_declared=pack.runtime_backend,
        backend_readiness=backend_state,
        hashes_verified=verify_hashes and required_state is VisualPackIntegrityState.VERIFIED,
        warnings=tuple(warnings),
        errors=tuple(errors),
    )
