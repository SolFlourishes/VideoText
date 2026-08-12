"""Explicit, provider-neutral translation-provider registration and creation."""

from __future__ import annotations

import re
from typing import Callable

from translation_contract import TranslationProvider


_PROVIDER_NAME = re.compile(r"^[a-z][a-z0-9_-]*$")
TranslationProviderFactory = Callable[[], TranslationProvider]


class TranslationProviderRegistryError(ValueError):
    """Base error for predictable translation-provider registry failures."""


class UnknownTranslationProviderError(TranslationProviderRegistryError):
    """Raised when explicit selection names no registered provider."""


class DuplicateTranslationProviderError(TranslationProviderRegistryError):
    """Raised when a canonical provider name is registered twice."""


class TranslationProviderCreationError(TranslationProviderRegistryError):
    """Raised when a factory cannot create a valid provider adapter."""


def normalize_provider_name(name: str) -> str:
    """Return the stable lowercase selection identifier for a provider name."""

    if not isinstance(name, str):
        raise ValueError("Provider name must be a string.")
    normalized = name.strip().lower()
    if not _PROVIDER_NAME.fullmatch(normalized):
        raise ValueError("Provider name must use lowercase letters, digits, hyphens, or underscores.")
    return normalized


class TranslationProviderRegistry:
    """An isolated registry of zero-argument factories, never provider instances."""

    def __init__(self) -> None:
        self._factories: dict[str, TranslationProviderFactory] = {}

    def register(self, name: str, factory: TranslationProviderFactory) -> None:
        """Register one factory under a normalized provider identity."""

        normalized = normalize_provider_name(name)
        if not callable(factory):
            raise ValueError("Translation provider factory must be callable.")
        if normalized in self._factories:
            raise DuplicateTranslationProviderError(f"Translation provider is already registered: {normalized}.")
        self._factories[normalized] = factory

    def discover(self) -> tuple[str, ...]:
        """Return registered names in sorted order without invoking any factory."""

        return tuple(sorted(self._factories))

    def create(self, name: str) -> TranslationProvider:
        """Create one explicitly selected provider and validate its identity."""

        normalized = normalize_provider_name(name)
        try:
            factory = self._factories[normalized]
        except KeyError as error:
            available = ", ".join(self.discover()) or "none"
            raise UnknownTranslationProviderError(
                f"Unknown translation provider: {normalized}. Available providers: {available}."
            ) from error
        try:
            provider = factory()
            provider_id = provider.provider_id
            translate = provider.translate
        except Exception as error:
            raise TranslationProviderCreationError(
                f"Could not create translation provider: {normalized}."
            ) from error
        if not isinstance(provider_id, str) or not provider_id.strip() or not callable(translate):
            raise TranslationProviderCreationError(
                f"Translation provider is invalid: {normalized}. It must expose a non-empty provider_id and callable translate."
            )
        if provider_id != normalized:
            raise TranslationProviderCreationError(
                f"Translation provider identity mismatch: registered as {normalized}, returned {provider_id!r}."
            )
        return provider


# Intentionally empty for 38C. Future application composition may register
# adapters explicitly; import and discovery perform no optional SDK loading.
application_translation_provider_registry = TranslationProviderRegistry()
