"""Focused fake-provider tests for headless visual orchestration."""

from pathlib import Path
import pickle
from types import SimpleNamespace
import sys
import unittest
from unittest.mock import patch

import numpy as np


sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from models import CandidateFrame, OCRResult, Presentation, Slide, SlideBuild
from visual_candidate_detection import (
    DETECTOR_REVISION,
    VisualAnalysisTarget,
    VisualCandidateAssessment,
    VisualCandidateDisposition,
    VisualSelectionScope,
)
from visual_evidence import project_candidate_frame_evidence
from visual_understanding_contract import (
    VisualAnalysisRequest,
    VisualAnalysisStatus,
    VisualAnalysisWarning,
    VisualContentType,
    VisualDetectionSignal,
    VisualRelationship,
    VisualUnderstandingResult,
    to_json_compatible,
)
from visual_understanding_pipeline import (
    VisualUnderstandingJob,
    build_visual_analysis_request,
    run_visual_understanding_job,
)


def make_frame(frame_number, text="54%"):
    image = np.full((24, 32, 3), 255, dtype=np.uint8)
    image[5:20, 8:25] = (frame_number % 255, 80, 160)
    return CandidateFrame(
        frame_number=frame_number,
        timestamp=frame_number / 5,
        image=image,
        difference_score=0.0,
        ocr_results=[OCRResult(text, 0.95, np.array([2, 2, 15, 8], dtype=float))],
    )


def make_target(
    frame_number,
    *,
    slide_number=1,
    build_index=0,
    disposition=VisualCandidateDisposition.RECOMMENDED,
    source_reference="result:module-2",
):
    projected = project_candidate_frame_evidence(
        make_frame(frame_number),
        source_reference=source_reference,
        checkpoint_path="module-2/cache/reading_order.pkl",
        slide_number=slide_number,
        build_index=build_index,
    )
    assessment = VisualCandidateAssessment(
        disposition=disposition,
        reasons=("synthetic_observable_evidence",),
        signals=(VisualDetectionSignal(
            "ocr_coverage",
            "Synthetic observable OCR geometry.",
            {"coverage_ratio": 0.1},
            DETECTOR_REVISION,
        ),),
        explanation="Synthetic deterministic triage.",
    )
    return VisualAnalysisTarget(projected, assessment)


def make_job(*targets):
    return VisualUnderstandingJob(
        job_id="module-2-visual",
        targets=tuple(targets),
        scope=VisualSelectionScope.RECOMMENDED,
        provider_id="fake-vision",
        interpretation_language="en",
    )


class RecordingSuccessProvider:
    provider_id = "fake-vision"

    def __init__(self):
        self.requests = []

    def analyze(self, request):
        self.requests.append(request)
        content_types = {
            10: VisualContentType.CHART_OR_GRAPH,
            20: VisualContentType.DIAGRAM_OR_PROCESS,
            30: VisualContentType.MIXED_OR_UNCERTAIN,
            40: VisualContentType.TEXT_ONLY,
        }
        content_type = content_types.get(request.evidence.frame_number, VisualContentType.MIXED_OR_UNCERTAIN)
        return VisualUnderstandingResult(
            request=request,
            status=VisualAnalysisStatus.SUCCESS,
            provider_id=self.provider_id,
            model_id="fake-model",
            content_type=content_type,
            description=f"Synthetic interpretation for frame {request.evidence.frame_number}.",
            relationships=(VisualRelationship("54%", "corresponds to", "category A"),),
            structured_details={"frame": request.evidence.frame_number, "years": [1940, 2020]},
            warnings=(VisualAnalysisWarning("synthetic_review", "Synthetic output requires review."),),
            provider_metadata={"response_id": f"fake-{request.evidence.frame_number}"},
        )


class PartialFailureProvider(RecordingSuccessProvider):
    def analyze(self, request):
        self.requests.append(request)
        if request.evidence.frame_number == 20:
            raise RuntimeError("unsafe provider detail should not be copied")
        return super().analyze(request)


class VisualUnderstandingPipelineTests(unittest.TestCase):
    def test_job_sorts_targets_and_request_ids_are_stable(self):
        third = make_target(30, slide_number=2)
        second = make_target(20, slide_number=1, build_index=1)
        first = make_target(10, slide_number=1, build_index=0)
        job = make_job(third, second, first)

        requests = tuple(
            build_visual_analysis_request(job, target, index)
            for index, target in enumerate(job.targets)
        )

        self.assertEqual((10, 20, 30), tuple(value.evidence.frame_number for value in requests))
        self.assertEqual(
            "module-2-visual:visual:0:slide:1:build:0:frame:10",
            requests[0].request_id,
        )
        self.assertEqual("en", requests[0].interpretation_language)

    def test_same_frame_coordinates_from_different_sources_are_distinct(self):
        first = make_target(10, source_reference="result:module-1")
        second = make_target(10, source_reference="result:module-2")

        job = make_job(second, first)

        self.assertEqual(
            ("result:module-1", "result:module-2"),
            tuple(target.evidence.reference.source_reference for target in job.targets),
        )

    def test_request_reuses_detached_evidence_without_reencoding(self):
        target = make_target(10)
        job = make_job(target)

        request = build_visual_analysis_request(job, job.targets[0], 0)

        self.assertIs(target.evidence.reference, request.evidence)
        self.assertIs(target.evidence.image_bytes, request.image_bytes)
        self.assertEqual(target.evidence.ocr_text, request.ocr_text)
        self.assertIs(target.evidence.ocr_regions, request.ocr_regions)
        self.assertIs(target.assessment.signals, request.detection_signals)
        self.assertEqual(target.evidence.reference.submitted_image_sha256,
                         request.evidence.submitted_image_sha256)

    def test_recording_provider_receives_ordered_exact_evidence(self):
        provider = RecordingSuccessProvider()
        job = make_job(
            make_target(30, slide_number=3),
            make_target(10, slide_number=1),
            make_target(20, slide_number=2),
        )

        result = run_visual_understanding_job(job, provider)

        self.assertEqual((10, 20, 30), tuple(
            value.evidence.frame_number for value in provider.requests
        ))
        self.assertEqual((10, 20, 30), tuple(
            value.evidence.frame_number for value in result.results
        ))
        self.assertEqual(3, result.success_count)
        self.assertEqual(0, result.failure_count)
        for request in provider.requests:
            self.assertEqual(request.evidence.submitted_image_sha256,
                             request.evidence.authoritative_image_sha256)
            self.assertEqual("54%", request.ocr_text)
            self.assertEqual("ocr_coverage", request.detection_signals[0].code)

    def test_per_request_exception_is_safe_and_later_frames_continue(self):
        provider = PartialFailureProvider()
        job = make_job(make_target(10), make_target(20, slide_number=2), make_target(30, slide_number=3))

        result = run_visual_understanding_job(job, provider)

        self.assertEqual(2, result.success_count)
        self.assertEqual(1, result.failure_count)
        self.assertEqual(3, result.submitted_count)
        failed = result.results[1]
        self.assertEqual(VisualAnalysisStatus.FAILURE, failed.status)
        self.assertIsNone(failed.content_type)
        self.assertIsNone(failed.description)
        self.assertNotIn("unsafe provider detail", failed.error)
        self.assertEqual(30, result.results[2].evidence.frame_number)

    def test_provider_returned_failure_is_preserved_and_execution_continues(self):
        class FailureResultProvider(RecordingSuccessProvider):
            def analyze(self, request):
                self.requests.append(request)
                if request.evidence.frame_number == 10:
                    return VisualUnderstandingResult(
                        request=request,
                        status=VisualAnalysisStatus.FAILURE,
                        provider_id=self.provider_id,
                        model_id="fake-model",
                        error="safe categorized failure",
                    )
                return super().analyze(request)

        provider = FailureResultProvider()
        result = run_visual_understanding_job(
            make_job(make_target(10), make_target(20, slide_number=2)), provider,
        )

        self.assertEqual((VisualAnalysisStatus.FAILURE, VisualAnalysisStatus.SUCCESS),
                         tuple(value.status for value in result.results))

    def test_incompatible_result_becomes_frame_failure(self):
        class InvalidProvider:
            provider_id = "fake-vision"

            def analyze(self, _request):
                return SimpleNamespace(status=VisualAnalysisStatus.SUCCESS)

        result = run_visual_understanding_job(make_job(make_target(10)), InvalidProvider())

        self.assertEqual(1, result.failure_count)
        self.assertIn("incompatible result", result.results[0].error)

    def test_result_for_another_request_is_rejected(self):
        class WrongRequestProvider(RecordingSuccessProvider):
            def analyze(self, request):
                other = VisualAnalysisRequest(
                    request_id=request.request_id + ":wrong",
                    evidence=request.evidence,
                    image_bytes=request.image_bytes,
                    image_media_type=request.image_media_type,
                    ocr_text=request.ocr_text,
                    ocr_regions=request.ocr_regions,
                    detection_signals=request.detection_signals,
                )
                return VisualUnderstandingResult(
                    request=other,
                    status=VisualAnalysisStatus.SUCCESS,
                    provider_id=self.provider_id,
                    model_id="fake-model",
                    content_type=VisualContentType.CHART_OR_GRAPH,
                    description="Wrong request.",
                )

        result = run_visual_understanding_job(make_job(make_target(10)), WrongRequestProvider())

        self.assertEqual(1, result.failure_count)
        self.assertIn("different evidence", result.results[0].error)

    def test_mismatched_provider_identity_is_rejected_per_frame(self):
        class WrongIdentityProvider(RecordingSuccessProvider):
            def analyze(self, request):
                value = super().analyze(request)
                return VisualUnderstandingResult(
                    request=request,
                    status=value.status,
                    provider_id="other-provider",
                    model_id=value.model_id,
                    content_type=value.content_type,
                    description=value.description,
                )

        result = run_visual_understanding_job(make_job(make_target(10)), WrongIdentityProvider())

        self.assertEqual(1, result.failure_count)
        self.assertIn("mismatched provider identity", result.results[0].error)

    def test_job_provider_identity_mismatch_stops_before_requests(self):
        provider = RecordingSuccessProvider()
        provider.provider_id = "different-provider"

        with self.assertRaisesRegex(ValueError, "does not match"):
            run_visual_understanding_job(make_job(make_target(10)), provider)

        self.assertEqual([], provider.requests)

    def test_progress_starts_at_zero_and_advances_after_failures(self):
        progress = []
        result = run_visual_understanding_job(
            make_job(make_target(10), make_target(20, slide_number=2), make_target(30, slide_number=3)),
            PartialFailureProvider(),
            progress_callback=lambda completed, total: progress.append((completed, total)),
        )

        self.assertEqual([(0, 3), (1, 3), (2, 3), (3, 3)], progress)
        self.assertEqual(3, result.submitted_count)

    def test_cancellation_occurs_between_requests_and_preserves_completed_results(self):
        provider = RecordingSuccessProvider()
        checks = iter((False, True))
        progress = []

        result = run_visual_understanding_job(
            make_job(make_target(10), make_target(20, slide_number=2), make_target(30, slide_number=3)),
            provider,
            progress_callback=lambda completed, total: progress.append((completed, total)),
            cancel_check=lambda: next(checks),
        )

        self.assertTrue(result.cancelled)
        self.assertEqual(1, result.submitted_count)
        self.assertEqual(2, result.unsubmitted_count)
        self.assertEqual([(0, 3), (1, 3)], progress)
        self.assertEqual((10,), tuple(value.evidence.frame_number for value in result.results))

    def test_text_dominant_target_is_analyzed_when_supplied(self):
        target = make_target(40, disposition=VisualCandidateDisposition.TEXT_DOMINANT)
        job = VisualUnderstandingJob(
            "all-slides", (target,), VisualSelectionScope.ALL_SLIDES, "fake-vision",
        )

        result = run_visual_understanding_job(job, RecordingSuccessProvider())

        self.assertEqual(VisualContentType.TEXT_ONLY, result.results[0].content_type)

    def test_pipeline_does_not_mutate_source_presentation_or_target_evidence(self):
        source_frame = make_frame(10)
        presentation = Presentation(
            metadata={"source": "preserved"},
            slides=[Slide(1, 2.0, 2.0, builds=[SlideBuild([source_frame], "54%")])],
        )
        target = make_target(10)
        presentation_before = pickle.dumps(presentation)
        target_before = (
            target.evidence.reference,
            target.evidence.image_bytes,
            target.evidence.ocr_text,
            target.evidence.ocr_regions,
            tuple(
                (signal.code, to_json_compatible(signal.observed_values))
                for signal in target.assessment.signals
            ),
        )

        result = run_visual_understanding_job(make_job(target), RecordingSuccessProvider())

        self.assertEqual(presentation_before, pickle.dumps(presentation))
        self.assertEqual(target_before, (
            target.evidence.reference,
            target.evidence.image_bytes,
            target.evidence.ocr_text,
            target.evidence.ocr_regions,
            tuple(
                (signal.code, to_json_compatible(signal.observed_values))
                for signal in target.assessment.signals
            ),
        ))
        self.assertIs(target.evidence.reference, result.results[0].evidence)

    def test_pipeline_never_invokes_processing_stages(self):
        with (
            patch("processing_service.perform_ocr") as ocr,
            patch("processing_service.open_video") as open_video,
            patch("processing_service.analyze_video") as analyze_video,
            patch("processing_service.reconstruct_reading_order") as reading_order,
            patch("processing_service.consolidate_slides") as consolidate,
        ):
            run_visual_understanding_job(make_job(make_target(10)), RecordingSuccessProvider())

        for stage in (ocr, open_video, analyze_video, reading_order, consolidate):
            stage.assert_not_called()


if __name__ == "__main__":
    unittest.main()
