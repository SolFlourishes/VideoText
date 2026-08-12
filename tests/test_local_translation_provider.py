"""Focused offline catalog/provider tests using small deterministic fakes."""
from __future__ import annotations

from dataclasses import FrozenInstanceError
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from local_translation_provider import (LOCAL_PROVIDER_ID, LocalCTranslate2Provider,
    LocalModelNotInstalledError, LocalTranslationCatalog, LocalTranslationConfig,
    LocalTranslationModel, discover_local_translation_catalog)
from translation_contract import TranslationProvenance, TranslationRequest, TranslationSourceType, TranslationStatus
from translation_pipeline import execute_translation_requests


class _Translator:
    def __init__(self): self.calls = []
    def translate_batch(self, tokens, **kwargs):
        self.calls.append((tokens, kwargs))
        return [type("Result", (), {"hypotheses": [["translated"]]})()]


class _Tokenizer:
    def encode(self, text, out_type): return [text]
    def decode(self, values): return "Texto traducido"


class _Runtime:
    def __init__(self): self.translator = _Translator(); self.loads = 0
    def loader(self):
        outer = self
        class CT2:
            @staticmethod
            def Translator(path, device): outer.loads += 1; return outer.translator
        class SP:
            @staticmethod
            def SentencePieceProcessor(model_file): return _Tokenizer()
        return CT2, SP


class LocalTranslationProviderTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.path = self.root / "m2m100"; self.path.mkdir(); (self.path / "sentencepiece.bpe.model").write_text("test")
        runtime_codes = {"pt-BR": "pt", "es-419": "es", "es-ES": "es", "ko-KR": "ko", "nl-NL": "nl"}
        self.models = tuple(LocalTranslationModel("m2m100-418m", LOCAL_PROVIDER_ID, "en-US", target,
            "m2m100", "1", self.path, "MIT", metadata={"runtime_source_code": "en", "runtime_target_code": runtime_codes[target]})
            for target in runtime_codes)
        self.models += (LocalTranslationModel("locale-editor", LOCAL_PROVIDER_ID, "en-US", "en-CA",
            "localization", "1", self.path, "MIT"),)
        self.catalog = LocalTranslationCatalog(self.models)

    def request(self, target="es"):
        return TranslationRequest(f"request:{target}", "Source text", "en-US", target,
            TranslationProvenance("source:1", TranslationSourceType.OCR))

    def test_catalog_is_immutable_exact_and_multilingual(self):
        self.assertIn(("en-US", "pt-BR"), self.catalog.available_pairs())
        self.assertEqual("ko-KR", self.catalog.select(LOCAL_PROVIDER_ID, "en-US", "ko-KR").target_language)
        self.assertEqual("en-CA", self.catalog.select(LOCAL_PROVIDER_ID, "en-US", "en-CA").target_language)
        with self.assertRaises(LocalModelNotInstalledError): self.catalog.select(LOCAL_PROVIDER_ID, "en-US", "fr")
        with self.assertRaises(LocalModelNotInstalledError): self.catalog.select(LOCAL_PROVIDER_ID, "en-US", "es-MX")
        with self.assertRaises(FrozenInstanceError): self.models[0].model_id = "other"

    def test_manifest_discovery_is_deterministic_and_rejects_ambiguous_pairs(self):
        manifest = {"model_id":"m2m100-418m","provider_id":LOCAL_PROVIDER_ID,"model_family":"m2m100",
            "model_version":"1","license_identifier":"MIT","metadata":{"runtime_source_code":"en"},"language_pairs":[{"source":"en-US","target":"pt-BR","runtime_target_code":"pt"},{"source":"en-US","target":"ko-KR","runtime_target_code":"ko"}]}
        (self.path / "videotext-model.json").write_text(json.dumps(manifest), encoding="utf-8")
        catalog = discover_local_translation_catalog(self.root)
        self.assertEqual((("en-US", "ko-KR"), ("en-US", "pt-BR")), catalog.available_pairs())
        with self.assertRaises(ValueError): LocalTranslationCatalog((self.models[0], self.models[0]))

    def test_lazy_offline_provider_preserves_request_and_model_provenance(self):
        runtime = _Runtime(); provider = LocalCTranslate2Provider(LocalTranslationConfig(self.root, self.catalog), runtime.loader)
        availability = provider.inspect_availability()
        self.assertTrue(availability.runtime_available); self.assertEqual(0, runtime.loads)
        request = self.request("ko-KR"); result = provider.translate(request)
        self.assertEqual(TranslationStatus.SUCCESS, result.status); self.assertIs(request, result.request)
        self.assertEqual("m2m100-418m", result.model_id); self.assertEqual(1, runtime.loads)
        self.assertEqual([["__en__", "Source text", "</s>"]], runtime.translator.calls[0][0])
        self.assertEqual([["__ko__"]], runtime.translator.calls[0][1]["target_prefix"])
        provider.translate(request); self.assertEqual(1, runtime.loads)

    def test_gui_style_manifest_inspection_does_not_load_the_runtime(self):
        runtime = _Runtime()
        provider = LocalCTranslate2Provider(
            LocalTranslationConfig(self.root, self.catalog), runtime.loader,
        )

        availability = provider.inspect_availability(verify_runtime=False)

        self.assertTrue(availability.runtime_available)
        self.assertEqual(self.models, availability.installed_models)
        self.assertEqual(0, runtime.loads)

    def test_missing_model_is_failure_without_network_or_cloud_fallback(self):
        runtime = _Runtime(); provider = LocalCTranslate2Provider(LocalTranslationConfig(self.root, self.catalog), runtime.loader)
        result = provider.translate(self.request("fr"))
        self.assertEqual(TranslationStatus.FAILURE, result.status); self.assertIsNone(result.translated_text)
        self.assertIn("Local translation model not installed", result.error); self.assertEqual(0, runtime.loads)
        batch = execute_translation_requests((self.request("fr"), self.request("fr")), provider)
        self.assertEqual(2, batch.failure_count)
