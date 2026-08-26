"""Optional, unregistered Argos Translate adapter for the translation spike."""
from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Any, Callable, Mapping

from translation_contract import TranslationRequest, TranslationResult, TranslationStatus

ARGOS_LANGUAGE_MAPPING_REVISION = "1"
ARGOS_LANGUAGE_CODES = {"en": "en", "es": "es", "de": "de"}

class ArgosProviderError(ValueError): pass
class ArgosDependencyUnavailableError(ArgosProviderError): pass
class ArgosPackageDirectoryError(ArgosProviderError): pass
class ArgosLanguageMappingError(ArgosProviderError): pass
class ArgosPackageUnavailableError(ArgosProviderError): pass
class ArgosPackageAmbiguityError(ArgosProviderError): pass

@dataclass(frozen=True)
class ArgosTranslationConfig:
    """Explicit local package location; no cache, download, or network policy."""
    package_directory: Path
    expected_package_identifiers: tuple[str, ...] = ()
    def __post_init__(self):
        if not isinstance(self.package_directory, Path): raise ValueError("package_directory must be a Path.")

@dataclass(frozen=True)
class ArgosPackageInfo:
    source_language: str; target_language: str; identifier: str | None; version: str | None

@dataclass(frozen=True)
class ArgosAvailability:
    dependency_available: bool; package_directory: Path; packages: tuple[ArgosPackageInfo, ...]; error: str | None = None

def map_argos_language(language: str) -> str:
    """Map only exact supported contract identifiers; regional variants fail."""
    try: return ARGOS_LANGUAGE_CODES[language]
    except KeyError as error: raise ArgosLanguageMappingError(f"Unsupported Argos language identifier: {language}.") from error

def _load_argos_runtime():
    """Lazily import Argos only when inspection/translation actually begins."""
    try:
        import argostranslate.package as package
        import argostranslate.translate as translate
        import importlib.metadata as metadata
    except ImportError as error: raise ArgosDependencyUnavailableError("Argos Translate is not installed.") from error
    return package, translate, metadata.version("argostranslate")

class ArgosTranslationProvider:
    """Unregistered direct-pair Argos adapter; no pivoting or package mutation."""
    provider_id = "argos"
    def __init__(self, config: ArgosTranslationConfig, runtime_loader: Callable[[], tuple[Any, Any, str]] = _load_argos_runtime):
        self._config=config; self._runtime_loader=runtime_loader
    def _packages(self):
        if not self._config.package_directory.is_dir():
            raise ArgosPackageDirectoryError(f"Argos package directory does not exist: {self._config.package_directory}")
        package, translate, version = self._runtime_loader()
        return package.get_installed_packages(self._config.package_directory), translate, version
    def inspect_availability(self) -> ArgosAvailability:
        """Inspect configured packages only; never loads models, downloads, or installs."""
        try:
            packages, _, _ = self._packages()
            return ArgosAvailability(True, self._config.package_directory, tuple(self._info(item) for item in packages))
        except ArgosProviderError as error: return ArgosAvailability(False, self._config.package_directory, (), str(error))
    def _info(self, package):
        return ArgosPackageInfo(str(package.from_code), str(package.to_code), getattr(package, "code", None), getattr(package, "package_version", None))
    def _select(self, packages, source: str, target: str):
        matches=[package for package in packages if getattr(package,"from_code",None)==source and getattr(package,"to_code",None)==target]
        if not matches: raise ArgosPackageUnavailableError(f"No direct Argos package is installed for {source} -> {target}.")
        if len(matches)!=1: raise ArgosPackageAmbiguityError(f"Multiple direct Argos packages are installed for {source} -> {target}.")
        return matches[0]
    def translate(self, request: TranslationRequest) -> TranslationResult:
        """Translate exactly one request, returning explicit request-level failures."""
        try:
            source=map_argos_language(request.source_language); target=map_argos_language(request.target_language)
            packages, translate_module, library_version=self._packages(); package=self._select(packages,source,target)
            # Argos currently exposes translation via its installed-language global state.
            # The explicit directory remains the authority for availability/selection;
            # a real 38D2 manual check must confirm it is also Argos's configured dir.
            translated=translate_module.get_translation_from_codes(source,target).translate(request.source_text)
            if not isinstance(translated,str) or not translated.strip(): raise RuntimeError("Argos returned an empty translation.")
            return TranslationResult(request,TranslationStatus.SUCCESS,"argos",translated,model_id=getattr(package,"package_version",None),provider_metadata=MappingProxyType({"library_version":library_version,"package_identifier":getattr(package,"code",None),"package_version":getattr(package,"package_version",None),"language_pair":f"{source}->{target}","mapping_revision":ARGOS_LANGUAGE_MAPPING_REVISION}))
        except Exception as error:
            return TranslationResult(request,TranslationStatus.FAILURE,"argos",error=f"{type(error).__name__}: {error}")
