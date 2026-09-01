"""Fake-sidecar tests for strict local visual understanding."""

import base64
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
from urllib.error import HTTPError
from unittest.mock import patch

import numpy as np


sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from local_visual_runtime import LocalVisualRuntime, LocalVisualRuntimeState
from local_visual_understanding_provider import (
    CHAT_COMPLETIONS_ENDPOINT,
    LOCAL_VISUAL_PROVIDER_ID,
    LocalVisualUnderstandingProvider,
    build_local_visual_prompt,
)
from models import CandidateFrame, OCRResult
from visual_candidate_detection import (
    DETECTOR_REVISION,
    VisualAnalysisTarget,
    VisualCandidateAssessment,
    VisualCandidateDisposition,
    VisualSelectionScope,
)
from visual_capability_pack import (
    CAPABILITY_PACK_SCHEMA,
    CAPABILITY_PACK_SCHEMA_VERSION,
    CURRENT_VISUAL_PROMPT_SCHEMA_REVISION,
    VISUAL_CAPABILITY,
    VISUAL_PACK_MANIFEST_FILENAME,
    check_visual_capability_pack_readiness,
    load_visual_capability_pack_manifest,
)
from visual_evidence import project_candidate_frame_evidence
from visual_understanding_contract import (
    VisualAnalysisStatus,
    VisualContentType,
    VisualDetectionSignal,
    VisualUnderstandingProvider,
)
from visual_understanding_pipeline import VisualUnderstandingJob, run_visual_understanding_job


class FakeResponse:
    def __init__(self, value):
        self.body = json.dumps(value, ensure_ascii=False).encode("utf-8")
        self.offset = 0
    def __enter__(self): return self
    def __exit__(self, *args): return False
    def read(self, size=-1):
        if size < 0: size = len(self.body) - self.offset
        value = self.body[self.offset:self.offset + size]
        self.offset += len(value)
        return value


class QueueOpener:
    def __init__(self, *responses):
        self.responses = list(responses)
        self.requests = []
    def __call__(self, request, timeout):
        self.requests.append((request, timeout, json.loads(request.data.decode("utf-8"))))
        response = self.responses.pop(0)
        if isinstance(response, BaseException):
            raise response
        return FakeResponse(response)


def structured(content_type="chart_or_graph", description="A chart compares categories.",
               relationships=None, details=None, warnings=None):
    return json.dumps({
        "content_type": content_type,
        "description": description,
        "relationships": relationships or [],
        "structured_details": details or {},
        "warnings": warnings or [],
    }, ensure_ascii=False, allow_nan=False)


def envelope(content, **message_fields):
    return {"choices": [{"message": {"content": content, **message_fields}}]}


def target(frame_number, *, ocr_text="Revenue 54% — Café"):
    image = np.full((30, 40, 3), 245, dtype=np.uint8)
    image[4:25, 8:32] = (frame_number, 80, 170)
    frame = CandidateFrame(
        frame_number, frame_number / 5, image, 0.0,
        [OCRResult(ocr_text, 0.93, np.array([2, 3, 30, 12], dtype=float))],
    )
    evidence = project_candidate_frame_evidence(
        frame, source_reference="result:module", checkpoint_path="result/cache/reading_order.pkl",
        slide_number=frame_number // 10, build_index=0,
    )
    signal = VisualDetectionSignal("dispersed_numeric_labels", "Numeric labels are separated.",
                                   {"count": 4}, DETECTOR_REVISION)
    assessment = VisualCandidateAssessment(
        VisualCandidateDisposition.RECOMMENDED, (signal.code,), (signal,), DETECTOR_REVISION,
        "Observable structure warrants analysis.",
    )
    return VisualAnalysisTarget(evidence, assessment)


class LocalVisualUnderstandingProviderTests(unittest.TestCase):
    def setUp(self):
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary_directory.cleanup)
        self.root = Path(self.temporary_directory.name).resolve()

    def pack(self, *, prompt_revisions=None, media_types=None):
        root = self.root / f"pack-{len(tuple(self.root.iterdir()))}"
        paths = {
            "runtime/llama-server.exe": b"runtime",
            "models/model.gguf": b"model",
            "models/mmproj.gguf": b"projector",
            "LICENSES/NOTICE.md": b"notice",
        }
        for relative, content in paths.items():
            path = root / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(content)
        document = {
            "schema": CAPABILITY_PACK_SCHEMA, "schema_version": CAPABILITY_PACK_SCHEMA_VERSION,
            "capability": VISUAL_CAPABILITY, "pack_id": "fake-local-vision", "pack_version": "1.0.0",
            "provider_id": "local-llama-cpp-vision",
            "runtime": {"family": "llama.cpp", "version": "fake-b1", "backend": "cpu",
                        "executable": "runtime/llama-server.exe"},
            "model": {"id": "fake-vlm", "family": "fake-family", "revision": "fake-revision",
                      "model_file": "models/model.gguf", "projector_file": "models/mmproj.gguf",
                      "license": "MIT", "source_repository": "local:test",
                      "redistribution_provenance": "Synthetic fixture."},
            "supported_prompt_schema_revisions": prompt_revisions or [CURRENT_VISUAL_PROMPT_SCHEMA_REVISION],
            "supported_image_media_types": media_types or ["image/png"],
            "minimum_videotext_version": "1.7.2", "network_required": False,
            "files": [{"path": relative, "sha256": hashlib.sha256(content).hexdigest()}
                      for relative, content in paths.items()],
            "license_notice_paths": ["LICENSES/NOTICE.md"],
        }
        manifest = root / VISUAL_PACK_MANIFEST_FILENAME
        manifest.write_text(json.dumps(document), encoding="utf-8")
        pack = load_visual_capability_pack_manifest(manifest)
        readiness = check_visual_capability_pack_readiness(
            pack,
            requested_prompt_schema=pack.supported_prompt_schema_revisions[0],
            requested_image_media_type=pack.supported_image_media_types[0],
        )
        return pack, readiness

    def provider(self, *responses, prompt_revisions=None, media_types=None):
        pack, readiness = self.pack(prompt_revisions=prompt_revisions, media_types=media_types)
        opener = QueueOpener(*responses)
        runtime = LocalVisualRuntime(pack, readiness, opener=opener)
        runtime._state = LocalVisualRuntimeState.READY
        runtime._port = 23456
        runtime._authentication_token = "private-test-token-" + "x" * 40
        return LocalVisualUnderstandingProvider(runtime, request_timeout=1.0), runtime, opener

    def job(self, *targets):
        return VisualUnderstandingJob(
            "local-provider-job", tuple(targets), VisualSelectionScope.RECOMMENDED,
            LOCAL_VISUAL_PROVIDER_ID, "en-CA", CURRENT_VISUAL_PROMPT_SCHEMA_REVISION, "1.8.0-dev",
        )

    def request(self, provider, current=None):
        job = self.job(current or target(10))
        from visual_understanding_pipeline import build_visual_analysis_request
        return build_visual_analysis_request(job, job.targets[0], 0)

    def test_provider_satisfies_existing_protocol_and_valid_chart_fields_parse(self):
        content = structured(
            relationships=[{"subject": "54%", "relation": "belongs to", "object": "Category A"}],
            details={"series": [{"label": "Category A", "value": 54}]},
            warnings=[{"code": "review_recommended", "message": "Legend is ambiguous.",
                       "details": {"items": 1}}],
        )
        provider, _, _ = self.provider(envelope(content))

        result = provider.analyze(self.request(provider))

        self.assertIsInstance(provider, VisualUnderstandingProvider)
        self.assertEqual(VisualAnalysisStatus.SUCCESS, result.status)
        self.assertEqual(VisualContentType.CHART_OR_GRAPH, result.content_type)
        self.assertEqual("Category A", result.relationships[0].object)
        self.assertEqual(54, result.structured_details["series"][0]["value"])
        self.assertEqual("review_recommended", result.warnings[0].code)

    def test_all_approved_visual_types_parse_without_type_specific_schema(self):
        cases = (
            "diagram_or_process", "table", "meaningful_figure_or_photo", "mixed_or_uncertain", "text_only",
            "decorative_or_background",
        )
        provider, _, _ = self.provider(*(envelope(structured(value, f"Description for {value}.")) for value in cases))
        request = self.request(provider)
        for value in cases:
            with self.subTest(value=value):
                result = provider.analyze(request)
                self.assertEqual(VisualAnalysisStatus.SUCCESS, result.status)
                self.assertEqual(value, result.content_type.value)

    def test_strict_invalid_outputs_fail_without_fabricated_interpretation(self):
        invalid = (
            ("{bad", "malformed_response"),
            ("prose " + structured(), "malformed_response"),
            ("```json\n" + structured() + "\n```", "malformed_response"),
            (structured("invented_type"), "invalid_structured_output"),
            (json.dumps({"content_type": "table", "description": [], "relationships": [],
                         "structured_details": {}, "warnings": []}), "invalid_structured_output"),
            (json.dumps({"content_type": "table"}), "invalid_structured_output"),
            ('{"content_type":"table","content_type":"chart_or_graph","description":"x",'
             '"relationships":[],"structured_details":{},"warnings":[]}', "invalid_structured_output"),
            ('{"content_type":"table","description":"x","relationships":[],'
             '"structured_details":{"bad":NaN},"warnings":[]}', "invalid_structured_output"),
        )
        provider, _, _ = self.provider(*(envelope(value) for value, _ in invalid))
        request = self.request(provider)
        for _, category in invalid:
            result = provider.analyze(request)
            self.assertEqual(VisualAnalysisStatus.FAILURE, result.status)
            self.assertTrue(result.error.startswith(category + ":"), result.error)
            self.assertIsNone(result.content_type)
            self.assertIsNone(result.description)
            self.assertEqual((), result.relationships)

    def test_explicit_model_refusal_is_failure(self):
        provider, _, _ = self.provider(envelope("", refusal="I cannot interpret this image."))

        result = provider.analyze(self.request(provider))

        self.assertEqual(VisualAnalysisStatus.FAILURE, result.status)
        self.assertTrue(result.error.startswith("model_refusal:"))
        self.assertNotIn("I cannot", result.error)

    def test_runtime_http_timeout_and_authentication_failures_are_safe(self):
        timeout = TimeoutError("raw OCR and token should never appear")
        auth = HTTPError("http://127.0.0.1", 401, "secret", {}, None)
        provider, runtime, _ = self.provider(timeout)
        request = self.request(provider)
        private_token = runtime._authentication_token

        timed_out = provider.analyze(request)
        auth_provider, _auth_runtime, _ = self.provider(auth)
        rejected = auth_provider.analyze(self.request(auth_provider))

        self.assertTrue(timed_out.error.startswith("request_timeout:"))
        self.assertTrue(rejected.error.startswith("authentication_failed:"))
        self.assertNotIn(private_token, timed_out.error + rejected.error)
        self.assertNotIn(request.ocr_text, timed_out.error + rejected.error)

    def test_unsupported_prompt_media_and_not_ready_fail_before_http(self):
        provider, runtime, opener = self.provider(
            envelope(structured()), prompt_revisions=["other-revision"], media_types=["image/jpeg"]
        )
        request = self.request(provider)

        prompt = provider.analyze(request)
        self.assertTrue(prompt.error.startswith("unsupported_prompt_schema:"))
        self.assertEqual([], opener.requests)

        runtime.pack.supported_prompt_schema_revisions  # immutable evidence retained
        provider2, runtime2, opener2 = self.provider(
            envelope(structured()), media_types=["image/jpeg"]
        )
        request2 = self.request(provider2)
        media = provider2.analyze(request2)
        self.assertTrue(media.error.startswith("unsupported_media_type:"))
        self.assertEqual([], opener2.requests)
        provider3, runtime3, _ = self.provider(envelope(structured()))
        request3 = self.request(provider3)
        runtime3._state = LocalVisualRuntimeState.STOPPED
        stopped = provider3.analyze(request3)
        self.assertTrue(stopped.error.startswith("runtime_not_ready:"))

    def test_exact_png_and_ocr_context_are_transport_only_and_request_unchanged(self):
        provider, _, opener = self.provider(envelope(structured()))
        request = self.request(provider)
        before = (request.image_bytes, request.evidence, request.ocr_text, request.ocr_regions)

        result = provider.analyze(request)
        transport = opener.requests[0][2]
        content = transport["messages"][0]["content"]
        prompt = content[0]["text"]
        data_url = content[1]["image_url"]["url"]

        self.assertEqual(VisualAnalysisStatus.SUCCESS, result.status)
        self.assertEqual(request.image_bytes, base64.b64decode(data_url.split(",", 1)[1]))
        self.assertTrue(data_url.startswith("data:image/png;base64,"))
        self.assertIn(request.ocr_text, prompt)
        self.assertIn('"confidence":0.93', prompt)
        self.assertIn("All five top-level keys are mandatory", prompt)
        self.assertIn("Use [] when there are no relationships or warnings", prompt)
        self.assertIn("do not invent a warning", prompt)
        self.assertEqual(before, (request.image_bytes, request.evidence, request.ocr_text, request.ocr_regions))

    def test_prompt_is_bounded_deterministically_without_mutating_ocr(self):
        provider, _, _ = self.provider(envelope(structured()))
        current = target(10, ocr_text="x" * 13_000)
        request = self.request(provider, current)
        original = request.ocr_text

        prompt = build_local_visual_prompt(request)

        self.assertIn('"ocr_text_truncated":true', prompt)
        self.assertLess(len(prompt), 20_000)
        self.assertEqual(original, request.ocr_text)

    def test_local_model_and_pack_provenance_preserved_on_success_and_failure(self):
        provider, _, _ = self.provider(envelope(structured()), envelope("bad"))
        request = self.request(provider)

        success = provider.analyze(request)
        failure = provider.analyze(request)

        for result in (success, failure):
            self.assertEqual(LOCAL_VISUAL_PROVIDER_ID, result.provider_id)
            self.assertEqual("fake-vlm", result.model_id)
            metadata = result.provider_metadata
            self.assertEqual("1.0.0", metadata["pack_version"])
            self.assertEqual("fake-b1", metadata["runtime_version"])
            self.assertEqual("cpu", metadata["runtime_backend"])
            self.assertEqual("fake-revision", metadata["model_revision"])
            self.assertRegex(metadata["model_sha256"], r"^[0-9a-f]{64}$")
            self.assertRegex(metadata["projector_sha256"], r"^[0-9a-f]{64}$")
            self.assertEqual(CURRENT_VISUAL_PROMPT_SCHEMA_REVISION,
                             metadata["prompt_schema_revision"])
            self.assertFalse(any("path" in key for key in metadata))

    def test_sequential_orchestration_contains_failure_and_preserves_order_progress_evidence(self):
        provider, _, opener = self.provider(
            envelope(structured("chart_or_graph", "First.")),
            envelope("malformed"),
            envelope(structured("diagram_or_process", "Third.")),
        )
        targets = (target(10), target(20), target(30))
        job = self.job(*targets)
        progress = []
        hashes = tuple(item.evidence.reference.authoritative_image_sha256 for item in job.targets)

        result = run_visual_understanding_job(job, provider, progress_callback=lambda done, total: progress.append((done, total)))

        self.assertEqual((VisualAnalysisStatus.SUCCESS, VisualAnalysisStatus.FAILURE,
                          VisualAnalysisStatus.SUCCESS), tuple(item.status for item in result.results))
        self.assertEqual((10, 20, 30), tuple(item.evidence.frame_number for item in result.results))
        self.assertEqual([(0, 3), (1, 3), (2, 3), (3, 3)], progress)
        self.assertEqual(3, len(opener.requests))
        self.assertEqual(hashes, tuple(item.evidence.authoritative_image_sha256 for item in result.results))

    def test_orchestration_cancellation_remains_between_requests(self):
        provider, _, opener = self.provider(envelope(structured()), envelope(structured()))
        checks = iter((False, True))

        result = run_visual_understanding_job(
            self.job(target(10), target(20)), provider, cancel_check=lambda: next(checks)
        )

        self.assertTrue(result.cancelled)
        self.assertEqual(1, result.submitted_count)
        self.assertEqual(1, len(opener.requests))

    def test_provider_targets_loopback_only_and_has_no_processing_or_cloud_fallback(self):
        provider, _, opener = self.provider(envelope(structured()))
        request = self.request(provider)
        with (
            patch("processing_service.perform_ocr") as ocr,
            patch("processing_service.open_video") as video,
            patch("processing_service.analyze_video") as analysis,
            patch("processing_service.reconstruct_reading_order") as reading_order,
            patch("openai_translation_provider.OpenAITranslationProvider") as cloud,
        ):
            result = provider.analyze(request)

        self.assertEqual(VisualAnalysisStatus.SUCCESS, result.status)
        self.assertTrue(opener.requests[0][0].full_url.startswith("http://127.0.0.1:23456/"))
        self.assertTrue(opener.requests[0][0].full_url.endswith(CHAT_COMPLETIONS_ENDPOINT))
        for operation in (ocr, video, analysis, reading_order, cloud):
            operation.assert_not_called()

    def test_sensitive_request_and_response_content_are_not_in_errors_or_source_logging(self):
        secret_ocr = "PRIVATE OCR CONTENT"
        raw_response = "PRIVATE MODEL RESPONSE"
        provider, runtime, _ = self.provider(envelope(raw_response))
        request = self.request(provider, target(10, ocr_text=secret_ocr))

        result = provider.analyze(request)
        source = (Path(__file__).resolve().parent.parent / "src" /
                  "local_visual_understanding_provider.py").read_text(encoding="utf-8")

        self.assertEqual(VisualAnalysisStatus.FAILURE, result.status)
        self.assertNotIn(secret_ocr, result.error)
        self.assertNotIn(raw_response, result.error)
        self.assertNotIn(runtime._authentication_token, result.error)
        self.assertNotIn("import logging", source)
        self.assertNotIn("OpenAITranslationProvider", source)
        self.assertNotIn("download", source.casefold())


if __name__ == "__main__":
    unittest.main()
