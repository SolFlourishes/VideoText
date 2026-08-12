"""Focused tests for isolated translation-provider registration and creation."""

from __future__ import annotations

from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from translation_contract import TranslationProvenance, TranslationRequest, TranslationResult, TranslationSourceType, TranslationStatus
from translation_pipeline import execute_translation_requests
from translation_provider_registry import (
    DuplicateTranslationProviderError,
    TranslationProviderCreationError,
    TranslationProviderRegistry,
    UnknownTranslationProviderError,
)


class FakeProvider:
    def __init__(self, provider_id="fake"):
        self.provider_id = provider_id

    def translate(self, request):
        return TranslationResult(request, TranslationStatus.SUCCESS, self.provider_id, f"translated:{request.source_text}")


class TranslationProviderRegistryTests(unittest.TestCase):
    def request(self):
        return TranslationRequest("source:1:translation:fr", "Source", "en", "fr", TranslationProvenance("source:1", TranslationSourceType.OCR))

    def test_register_discover_and_create_are_deterministic(self):
        registry = TranslationProviderRegistry()
        created = []
        registry.register("Zeta", lambda: created.append("zeta") or FakeProvider("zeta"))
        registry.register("fake", lambda: created.append("fake") or FakeProvider())
        self.assertEqual(("fake", "zeta"), registry.discover())
        self.assertEqual([], created)
        provider = registry.create(" FAKE ")
        self.assertEqual("fake", provider.provider_id)
        self.assertEqual(["fake"], created)

    def test_errors_cover_unknown_duplicate_and_blank_names(self):
        registry = TranslationProviderRegistry()
        registry.register("fake", lambda: FakeProvider())
        with self.assertRaises(DuplicateTranslationProviderError):
            registry.register("FAKE", lambda: FakeProvider())
        with self.assertRaisesRegex(UnknownTranslationProviderError, "Available providers: fake"):
            registry.create("missing")
        with self.assertRaises(ValueError):
            registry.register(" ", lambda: FakeProvider())

    def test_factory_failures_are_chained_and_invalid_providers_are_rejected(self):
        registry = TranslationProviderRegistry()
        def broken():
            raise RuntimeError("missing optional dependency")
        registry.register("broken", broken)
        registry.register("invalid", lambda: object())
        registry.register("mismatch", lambda: FakeProvider("other"))
        with self.assertRaises(TranslationProviderCreationError) as failure:
            registry.create("broken")
        self.assertIsInstance(failure.exception.__cause__, RuntimeError)
        for name in ("invalid", "mismatch"):
            with self.assertRaises(TranslationProviderCreationError):
                registry.create(name)

    def test_registry_instances_are_isolated_and_one_failure_does_not_block_another(self):
        first = TranslationProviderRegistry(); second = TranslationProviderRegistry()
        first.register("broken", lambda: (_ for _ in ()).throw(RuntimeError("broken")))
        second.register("fake", lambda: FakeProvider())
        self.assertEqual(("broken",), first.discover())
        self.assertEqual(("fake",), second.discover())
        with self.assertRaises(TranslationProviderCreationError):
            first.create("broken")
        self.assertEqual("fake", second.create("fake").provider_id)

    def test_created_provider_works_without_changing_request_or_provenance(self):
        registry = TranslationProviderRegistry(); registry.register("fake", lambda: FakeProvider())
        request = self.request()
        result = execute_translation_requests((request,), registry.create("fake"))
        self.assertEqual("translated:Source", result.results[0].translated_text)
        self.assertIs(request, result.results[0].request)
        self.assertEqual(TranslationSourceType.OCR, request.provenance.source_type)
