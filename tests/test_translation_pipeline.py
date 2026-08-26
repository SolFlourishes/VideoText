"""Focused deterministic source-selection and execution tests."""

from __future__ import annotations

from dataclasses import FrozenInstanceError
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from translation_contract import TranslationResult, TranslationStatus
from translation_pipeline import (
    TranslationSourceRecord,
    build_translation_requests,
    execute_translation_requests,
)


class FakeProvider:
    provider_id = "fake"

    def translate(self, request):
        if request.request_id.startswith("bad"):
            raise RuntimeError("provider unavailable")
        return TranslationResult(request, TranslationStatus.SUCCESS, self.provider_id, f"translated:{request.source_text}")


class TranslationPipelineTests(unittest.TestCase):
    def records(self):
        return (
            TranslationSourceRecord("slide:1/paragraph:1", "canonical", "verified", "edited", True, 0, {"slide": 1}),
            TranslationSourceRecord("slide:1/paragraph:2", "canonical", None, "accepted edit", True, 1),
            TranslationSourceRecord("slide:1/paragraph:3", "canonical fallback", " ", "ignored edit", False, 2),
            TranslationSourceRecord("slide:1/paragraph:4", " ", "", "", False, 3),
        )

    def test_source_selection_priority_and_exact_text(self):
        requests = build_translation_requests(self.records(), "en", "fr")
        self.assertEqual(["verified", "accepted edit", "canonical fallback"], [request.source_text for request in requests])
        self.assertEqual(["verified_ocr", "user_edit", "ocr"], [request.provenance.source_type.value for request in requests])
        self.assertEqual([0, 1, 2], [request.ordering_index for request in requests])
        self.assertEqual("slide:1/paragraph:1:translation:fr", requests[0].request_id)
        self.assertEqual(1, requests[0].provenance.context["slide"])

    def test_blank_optional_values_do_not_override_and_empty_records_skip(self):
        requests = build_translation_requests(self.records(), "en", "fr")
        self.assertEqual(3, len(requests))
        self.assertEqual("canonical fallback", requests[2].source_text)

    def test_execution_preserves_order_and_contains_provider_failures(self):
        requests = list(build_translation_requests(self.records(), "en", "fr"))
        requests[1] = type(requests[1])("bad:source:translation:fr", requests[1].source_text, requests[1].source_language, requests[1].target_language, requests[1].provenance, requests[1].ordering_index)
        batch = execute_translation_requests(requests, FakeProvider())
        self.assertEqual([request.request_id for request in requests], [result.request_id for result in batch.results])
        self.assertEqual((3, 2, 1), (batch.submitted_count, batch.success_count, batch.failure_count))
        self.assertIn("RuntimeError: provider unavailable", batch.results[1].error)
        self.assertEqual("accepted edit", batch.results[1].source_text)

    def test_requests_and_source_records_are_not_mutated(self):
        record = self.records()[0]
        request = build_translation_requests((record,), "en", "fr")[0]
        batch = execute_translation_requests((request,), FakeProvider())
        self.assertIs(request, batch.results[0].request)
        with self.assertRaises(FrozenInstanceError):
            request.source_text = "replacement"
        with self.assertRaises(TypeError):
            record.context["slide"] = 2

    def test_every_submitted_request_receives_one_result(self):
        requests = build_translation_requests(self.records(), "en", "fr")
        first = execute_translation_requests(requests, FakeProvider())
        second = execute_translation_requests(requests, FakeProvider())
        self.assertEqual(len(requests), len(first.results))
        self.assertEqual(first.results, second.results)
