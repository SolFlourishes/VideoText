"""Focused tests for the provider-neutral translation domain contract."""

from __future__ import annotations

from dataclasses import FrozenInstanceError
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from translation_contract import (
    TranslationProvenance,
    TranslationProvider,
    TranslationRequest,
    TranslationResult,
    TranslationSourceType,
    TranslationStatus,
)


class FakeTranslationProvider:
    provider_id = "fake"

    def translate(self, request: TranslationRequest) -> TranslationResult:
        return TranslationResult(request, TranslationStatus.SUCCESS, self.provider_id, "Bonjour")


class TranslationContractTests(unittest.TestCase):
    def request(self) -> TranslationRequest:
        return TranslationRequest(
            "slide-1-paragraph-2", "Hello", "en", "fr-CA",
            TranslationProvenance("slide:1/paragraph:2", TranslationSourceType.VERIFIED_OCR, {"slide_number": 1}),
            ordering_index=2,
        )

    def test_valid_request_preserves_identity_and_provenance(self) -> None:
        request = self.request()
        self.assertEqual("slide-1-paragraph-2", request.request_id)
        self.assertEqual(TranslationSourceType.VERIFIED_OCR, request.provenance.source_type)
        self.assertEqual(1, request.provenance.context["slide_number"])

    def test_empty_source_and_invalid_languages_are_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "source_text"):
            TranslationRequest("id", " ", "en", "fr", TranslationProvenance("source", TranslationSourceType.OCR))
        with self.assertRaisesRegex(ValueError, "source_language"):
            TranslationRequest("id", "Text", "english", "fr", TranslationProvenance("source", TranslationSourceType.OCR))

    def test_success_and_failure_results_are_explicit(self) -> None:
        request = self.request()
        success = TranslationResult(request, TranslationStatus.SUCCESS, "fake", "Bonjour", model_id="test-model")
        failure = TranslationResult(request, TranslationStatus.FAILURE, "fake", error="Network unavailable")
        self.assertEqual("Bonjour", success.translated_text)
        self.assertIsNone(failure.translated_text)
        self.assertEqual("Network unavailable", failure.error)

    def test_result_cannot_mutate_or_replace_source_evidence(self) -> None:
        request = self.request()
        result = TranslationResult(request, TranslationStatus.SUCCESS, "fake", "Bonjour", provider_metadata={"attempt": 1})
        self.assertEqual("Hello", result.source_text)
        with self.assertRaises(FrozenInstanceError):
            result.request = self.request()
        with self.assertRaises(TypeError):
            result.provider_metadata["attempt"] = 2
        with self.assertRaises(TypeError):
            request.provenance.context["slide_number"] = 2

    def test_minimal_fake_provider_uses_the_protocol(self) -> None:
        provider = FakeTranslationProvider()
        self.assertIsInstance(provider, TranslationProvider)
        result = provider.translate(self.request())
        self.assertEqual("fake", result.provider_id)
        self.assertEqual(self.request().request_id, result.request_id)
