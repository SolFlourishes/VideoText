"""Explicit, offline CTranslate2 local-translation provider and model catalog.

Models are external, approved files under a caller-selected root.  This module
never downloads models, accesses a cloud service, or falls back to OpenAI.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import json
import os
from pathlib import Path
from types import MappingProxyType
from typing import Any, Callable, Mapping

from translation_contract import TranslationRequest, TranslationResult, TranslationStatus


LOCAL_PROVIDER_ID = "local-ctranslate2"
LOCAL_CATALOG_REVISION = "local-translation-catalog-v1"
LOCAL_MANIFEST_FILENAME = "videotext-model.json"


def default_local_translation_model_root() -> Path:
    """Return the user-writable external location for approved local models."""

    configured = os.environ.get("VIDEOTEXT_TRANSLATION_MODELS")
    if configured and configured.strip():
        return Path(configured).expanduser().resolve()
    return (Path.home() / "AppData" / "Local" / "VideoText" / "models" / "translation").resolve()


class LocalTranslationError(ValueError):
    """Base error for explicit local-model resolution."""


class LocalRuntimeUnavailableError(LocalTranslationError):
    """Raised when CTranslate2 or SentencePiece is unavailable."""


class LocalModelNotInstalledError(LocalTranslationError):
    """Raised when no approved local model matches one exact language pair."""


class LocalModelAmbiguityError(LocalTranslationError):
    """Raised when more than one approved model matches a language pair."""


class LocalModelManifestError(LocalTranslationError):
    """Raised when an installed model manifest is malformed or unsafe."""


def _immutable_metadata(metadata: Mapping[str, Any]) -> Mapping[str, Any]:
    return MappingProxyType(dict(metadata))


@dataclass(frozen=True)
class LocalTranslationModel:
    """One approved exact language-pair mapping to an external local model."""

    model_id: str
    provider_id: str
    source_language: str
    target_language: str
    model_family: str
    model_version: str
    local_path: Path
    license_identifier: str
    mapping_revision: str = LOCAL_CATALOG_REVISION
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        for value, name in ((self.model_id, "model_id"), (self.provider_id, "provider_id"),
                            (self.source_language, "source_language"), (self.target_language, "target_language"),
                            (self.model_family, "model_family"), (self.model_version, "model_version"),
                            (self.license_identifier, "license_identifier"), (self.mapping_revision, "mapping_revision")):
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{name} is required.")
        if not isinstance(self.local_path, Path) or not self.local_path.is_absolute():
            raise ValueError("local_path must be an absolute Path.")
        if self.source_language == self.target_language:
            raise ValueError("local model source and target languages must differ.")
        if self.model_family == "m2m100" and (not isinstance(self.metadata.get("runtime_source_code"), str)
                                               or not isinstance(self.metadata.get("runtime_target_code"), str)):
            raise ValueError("m2m100 models require explicit runtime source and target code mappings.")
        object.__setattr__(self, "metadata", _immutable_metadata(self.metadata))


@dataclass(frozen=True)
class LocalTranslationCatalog:
    """Immutable approved model catalog with exact, deterministic pair lookup."""

    models: tuple[LocalTranslationModel, ...]
    revision: str = LOCAL_CATALOG_REVISION

    def __post_init__(self) -> None:
        if any(not isinstance(model, LocalTranslationModel) for model in self.models):
            raise ValueError("models must contain LocalTranslationModel values.")
        pairs = tuple((model.provider_id, model.source_language, model.target_language) for model in self.models)
        if len(pairs) != len(set(pairs)):
            raise ValueError("local model catalog cannot contain ambiguous language pairs.")

    def available_pairs(self, provider_id: str = LOCAL_PROVIDER_ID) -> tuple[tuple[str, str], ...]:
        """Return exact installed pairs in stable source/target order."""

        return tuple(sorted((model.source_language, model.target_language) for model in self.models
                            if model.provider_id == provider_id))

    def select(self, provider_id: str, source_language: str, target_language: str) -> LocalTranslationModel:
        """Return one exact approved match without regional fallback or guessing."""

        matches = tuple(model for model in self.models if (model.provider_id, model.source_language, model.target_language)
                        == (provider_id, source_language, target_language))
        if not matches:
            raise LocalModelNotInstalledError("Local translation model not installed for this language pair.")
        if len(matches) != 1:
            raise LocalModelAmbiguityError("Multiple local translation models match this language pair.")
        return matches[0]


def discover_local_translation_catalog(model_root: Path) -> LocalTranslationCatalog:
    """Read explicit manifests only; discovery never downloads or loads a model."""

    if not isinstance(model_root, Path):
        raise ValueError("model_root must be a Path.")
    if not model_root.is_dir():
        return LocalTranslationCatalog(())
    models: list[LocalTranslationModel] = []
    for manifest in sorted(model_root.rglob(LOCAL_MANIFEST_FILENAME)):
        try:
            data = json.loads(manifest.read_text(encoding="utf-8"))
            pairs = data["language_pairs"]
            if not isinstance(pairs, list) or not pairs:
                raise ValueError("language_pairs is required")
            relative_model_path = Path(data.get("model_path", "."))
            local_path = (manifest.parent / relative_model_path).resolve()
            if manifest.parent.resolve() not in (local_path, *local_path.parents):
                raise ValueError("model_path escapes the manifest directory")
            common = {key: data[key] for key in ("model_id", "provider_id", "model_family", "model_version", "license_identifier")}
            for pair in pairs:
                metadata = dict(data.get("metadata", {}))
                if "runtime_target_code" in pair:
                    metadata["runtime_target_code"] = pair["runtime_target_code"]
                models.append(LocalTranslationModel(
                    **common, source_language=pair["source"], target_language=pair["target"], local_path=local_path,
                    mapping_revision=data.get("mapping_revision", LOCAL_CATALOG_REVISION), metadata=metadata))
        except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
            raise LocalModelManifestError(f"Invalid local translation model manifest: {manifest}") from error
    return LocalTranslationCatalog(tuple(models))


@dataclass(frozen=True)
class LocalTranslationConfig:
    """Explicit external storage configuration for local translation models."""

    model_root: Path
    catalog: LocalTranslationCatalog | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.model_root, Path) or not self.model_root.is_absolute():
            raise ValueError("model_root must be an absolute Path.")


@dataclass(frozen=True)
class LocalTranslationAvailability:
    """Read-only local-provider state for application composition and GUI display."""

    runtime_available: bool
    model_root: Path
    installed_models: tuple[LocalTranslationModel, ...]
    error: str | None = None

    @property
    def installed_pairs(self) -> tuple[tuple[str, str], ...]:
        return tuple(sorted((model.source_language, model.target_language) for model in self.installed_models))


def inspect_installed_local_translation_models(model_root: Path) -> LocalTranslationAvailability:
    """Inspect manifests only, without importing the local runtime or loading a model."""

    try:
        catalog = discover_local_translation_catalog(model_root)
        return LocalTranslationAvailability(True, model_root, catalog.models)
    except LocalTranslationError as error:
        return LocalTranslationAvailability(False, model_root, (), str(error))


def _load_runtime():
    try:
        import ctranslate2
        import sentencepiece
    except ImportError as error:
        raise LocalRuntimeUnavailableError("Local translation runtime is not installed.") from error
    return ctranslate2, sentencepiece


class LocalCTranslate2Provider:
    """Offline exact-pair provider; model loading is lazy and cached by path."""

    provider_id = LOCAL_PROVIDER_ID

    def __init__(self, config: LocalTranslationConfig,
                 runtime_loader: Callable[[], tuple[Any, Any]] = _load_runtime) -> None:
        self._config = config
        self._runtime_loader = runtime_loader
        self._loaded: dict[Path, tuple[Any, Any]] = {}

    def _catalog(self) -> LocalTranslationCatalog:
        return self._config.catalog or discover_local_translation_catalog(self._config.model_root)

    def inspect_availability(self, verify_runtime: bool = True) -> LocalTranslationAvailability:
        """Inspect approved manifests without loading a model.

        The GUI uses ``verify_runtime=False`` during startup.  That avoids
        loading CTranslate2 native libraries before PaddleOCR has completed
        OCR.  Translation itself still validates and loads the runtime only
        when it is actually selected as the downstream stage.
        """

        try:
            catalog = self._catalog()
            if verify_runtime:
                self._runtime_loader()
            return LocalTranslationAvailability(True, self._config.model_root, catalog.models)
        except LocalTranslationError as error:
            return LocalTranslationAvailability(False, self._config.model_root, (), str(error))

    def _load_model(self, model: LocalTranslationModel) -> tuple[Any, Any]:
        if model.local_path in self._loaded:
            return self._loaded[model.local_path]
        if not model.local_path.is_dir():
            raise LocalModelNotInstalledError("Local translation model not installed for this language pair.")
        ctranslate2, sentencepiece = self._runtime_loader()
        tokenizer_path = model.local_path / "sentencepiece.bpe.model"
        if not tokenizer_path.is_file():
            raise LocalModelManifestError(f"Local translation model is missing sentencepiece.bpe.model: {model.local_path}")
        loaded = (ctranslate2.Translator(str(model.local_path), device="cpu"),
                  sentencepiece.SentencePieceProcessor(model_file=str(tokenizer_path)))
        self._loaded[model.local_path] = loaded
        return loaded

    def translate(self, request: TranslationRequest) -> TranslationResult:
        """Translate once locally; failures preserve request evidence without fallback."""

        try:
            model = self._catalog().select(self.provider_id, request.source_language, request.target_language)
            translator, tokenizer = self._load_model(model)
            source_tokens = tokenizer.encode(request.source_text, out_type=str)
            source_code = model.metadata.get("runtime_source_code")
            target_code = model.metadata.get("runtime_target_code")
            if model.model_family == "m2m100":
                source_tokens = [f"__{source_code}__", *source_tokens, "</s>"]
            target_prefix = [f"__{target_code}__"] if model.model_family == "m2m100" else None
            kwargs = {"target_prefix": [target_prefix]} if target_prefix else {}
            response = translator.translate_batch([source_tokens], **kwargs)
            output_tokens = response[0].hypotheses[0] if response else ()
            if model.model_family == "m2m100":
                output_tokens = tuple(token for token in output_tokens if token != "</s>" and not token.startswith("__"))
            translated = tokenizer.decode(list(output_tokens))
            if not isinstance(translated, str) or not translated.strip():
                raise RuntimeError("Local translation model returned an empty translation.")
            return TranslationResult(request, TranslationStatus.SUCCESS, self.provider_id, translated,
                model_id=model.model_id, provider_metadata=MappingProxyType({
                    "model_family": model.model_family, "model_version": model.model_version,
                    "model_path": str(model.local_path), "license_identifier": model.license_identifier,
                    "mapping_revision": model.mapping_revision,
                }))
        except Exception as error:
            return TranslationResult(request, TranslationStatus.FAILURE, self.provider_id,
                                     error=f"{type(error).__name__}: {error}")
