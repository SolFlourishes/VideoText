"""Focused tests for the standalone visual-understanding Markdown report."""

from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

import numpy as np


sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from models import CandidateFrame, OCRResult
from visual_candidate_detection import (
    DETECTOR_REVISION,
    VisualAnalysisTarget,
    VisualCandidateAssessment,
    VisualCandidateDisposition,
    VisualSelectionScope,
)
from visual_evidence import project_candidate_frame_evidence
from visual_understanding_contract import (
    VisualAnalysisStatus,
    VisualAnalysisWarning,
    VisualContentType,
    VisualDetectionSignal,
    VisualRelationship,
    VisualUnderstandingResult,
)
from visual_understanding_export import (
    REPORT_FILENAME,
    render_visual_understanding_markdown,
    write_visual_understanding_markdown,
)
from visual_understanding_pipeline import VisualUnderstandingJob, run_visual_understanding_job
from visual_understanding_store import load_visual_understanding_result, write_visual_understanding_result


def make_target(frame_number, *, source="result:module-a", text="OCR <source> — Café"):
    image = np.full((24, 32, 3), 240, dtype=np.uint8)
    image[4:20, 6:26] = (frame_number, 70, 140)
    frame = CandidateFrame(
        frame_number, frame_number / 4, image, 0.0,
        [OCRResult(text, 0.91, np.array([2, 2, 24, 9], dtype=float))],
    )
    evidence = project_candidate_frame_evidence(
        frame,
        source_reference=source,
        checkpoint_path=f"D:/runs/{source}/cache/reading_order.pkl",
        slide_number=frame_number // 10,
        build_index=1,
    )
    signal = VisualDetectionSignal(
        "dispersed_numeric_labels",
        "Numeric labels are spatially separated.",
        {"count": 4, "ratio": 0.25},
        DETECTOR_REVISION,
    )
    assessment = VisualCandidateAssessment(
        VisualCandidateDisposition.RECOMMENDED,
        ("dispersed_numeric_labels",),
        (signal,),
        DETECTOR_REVISION,
        "Observable structure warrants provider analysis.",
    )
    return VisualAnalysisTarget(evidence, assessment)


def make_job(*targets):
    return VisualUnderstandingJob(
        "visual-report-test",
        tuple(targets),
        VisualSelectionScope.RECOMMENDED,
        "fake-vision",
        "en-CA",
        "visual-understanding-test-v1",
        "1.8.0-dev",
    )


class ReportProvider:
    provider_id = "fake-vision"

    def analyze(self, request):
        if request.evidence.frame_number == 20:
            return VisualUnderstandingResult(
                request,
                VisualAnalysisStatus.FAILURE,
                self.provider_id,
                model_id="fake-model",
                error="Safe <b>failure</b> — no result.",
            )
        return VisualUnderstandingResult(
            request,
            VisualAnalysisStatus.SUCCESS,
            self.provider_id,
            model_id="fake-model",
            content_type=VisualContentType.CHART_OR_GRAPH,
            description="<script>alert('x')</script> Café **chart**",
            relationships=(VisualRelationship("54%", "corresponds to", "Catégorie A"),),
            structured_details={"series": [{"name": "Café", "values": [54, 46]}]},
            warnings=(VisualAnalysisWarning(
                "review_recommended", "Legend <em>mapping</em> needs review.", {"items": 1}
            ),),
        )


class VisualUnderstandingExportTests(unittest.TestCase):
    def setUp(self):
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary_directory.cleanup)
        self.root = Path(self.temporary_directory.name)
        self.workspace = self.root / "visual-understanding"

    def completed(self):
        return run_visual_understanding_job(
            make_job(make_target(10), make_target(20)), ReportProvider()
        )

    def test_full_and_partial_report_separates_evidence_signals_and_interpretation(self):
        text = render_visual_understanding_markdown(self.completed())

        self.assertIn("### Evidence", text)
        self.assertIn("### OCR Context", text)
        self.assertIn("OCR <source> — Café", text)
        self.assertIn("### Candidate Signals", text)
        self.assertIn("observable deterministic triage signals", text)
        self.assertIn("dispersed_numeric_labels", text)
        self.assertIn(DETECTOR_REVISION, text)
        self.assertIn("### AI-Derived Visual Interpretation", text)
        self.assertIn("not preserved source truth", text)
        self.assertIn("chart_or_graph", text)
        self.assertIn("#### Relationships", text)
        self.assertIn("Catégorie A", text)
        self.assertIn('"series": [', text)
        self.assertIn("#### Warnings", text)
        self.assertIn("review_recommended", text)
        self.assertIn("Safe <b>failure</b> — no result.", text)

    def test_failure_does_not_fabricate_interpretation(self):
        text = render_visual_understanding_markdown(self.completed())
        failure_section = text.split("## Slide 2", 1)[1]

        self.assertIn("Status: **Failure**", failure_section)
        self.assertIn("#### Safe Error", failure_section)
        self.assertNotIn("Visual type:", failure_section)
        self.assertNotIn("#### Description", failure_section)
        self.assertNotIn("#### Relationships", failure_section)

    def test_cancelled_unsubmitted_target_is_not_called_a_provider_failure(self):
        checks = iter((False, True))
        result = run_visual_understanding_job(
            make_job(make_target(10), make_target(20)),
            ReportProvider(),
            cancel_check=lambda: next(checks),
        )
        text = render_visual_understanding_markdown(result)

        self.assertIn("- Cancelled: Yes", text)
        self.assertIn("- Unsubmitted: 1", text)
        self.assertIn("Status: **Not submitted**", text)
        self.assertIn("is not a provider failure", text)
        self.assertNotIn("Status: **Failure**", text)

    def test_multiple_sources_and_exact_frame_provenance_are_clear(self):
        result = run_visual_understanding_job(
            make_job(make_target(10, source="result:module-a"),
                     make_target(30, source="result:module-b")),
            ReportProvider(),
        )
        text = render_visual_understanding_markdown(result)
        first = result.results[0].evidence

        self.assertIn("## Source — result:module-a", text)
        self.assertIn("## Source — result:module-b", text)
        self.assertIn("## Slide 1 — Build 1, Frame 10 at 2.5s", text)
        self.assertIn(first.authoritative_image_sha256, text)
        self.assertIn("reading_order.pkl", text)
        self.assertEqual(2, text.count("## Slide"))

    def test_evidence_link_is_relative_and_matches_stored_png(self):
        result = self.completed()
        json_path = write_visual_understanding_result(result, self.workspace)
        loaded = load_visual_understanding_result(json_path)
        report = write_visual_understanding_markdown(loaded, self.workspace)
        text = report.read_text(encoding="utf-8")
        evidence_names = {path.name for path in (self.workspace / "evidence").glob("*.png")}

        for name in evidence_names:
            self.assertIn(f"![Source frame](evidence/{name})", text)
        self.assertNotIn(str(self.workspace), text)

    def test_provider_html_and_markdown_are_in_non_rendering_code_blocks(self):
        text = render_visual_understanding_markdown(self.completed())

        self.assertIn("```text\n<script>alert('x')</script> Café **chart**\n```", text)
        self.assertIn("```text\nSafe <b>failure</b> — no result.\n```", text)
        self.assertNotIn("\n<script>alert('x')</script>\n", text)

    def test_existing_report_is_not_silently_overwritten(self):
        report = write_visual_understanding_markdown(self.completed(), self.workspace)
        before = report.read_bytes()

        with self.assertRaisesRegex(FileExistsError, "already exists"):
            write_visual_understanding_markdown(self.completed(), self.workspace)

        self.assertEqual(before, report.read_bytes())
        self.assertEqual(REPORT_FILENAME, report.name)

    def test_export_changes_no_source_or_stored_evidence_and_calls_no_processing(self):
        source = self.root / "source"
        source.mkdir()
        checkpoint = source / "reading_order.pkl"
        checkpoint.write_bytes(b"preserved")
        result = self.completed()
        write_visual_understanding_result(result, self.workspace)
        before = {path.relative_to(self.root): path.read_bytes()
                  for path in self.root.rglob("*") if path.is_file()}

        with (
            patch("processing_service.perform_ocr") as ocr,
            patch("processing_service.open_video") as video,
            patch("processing_service.analyze_video") as analysis,
            patch("processing_service.reconstruct_reading_order") as reading_order,
            patch.object(ReportProvider, "analyze") as provider,
        ):
            loaded = load_visual_understanding_result(self.workspace)
            write_visual_understanding_markdown(loaded, self.workspace)

        after_without_report = {path.relative_to(self.root): path.read_bytes()
                                for path in self.root.rglob("*")
                                if path.is_file() and path.name != REPORT_FILENAME}
        self.assertEqual(before, after_without_report)
        for operation in (ocr, video, analysis, reading_order, provider):
            operation.assert_not_called()


if __name__ == "__main__":
    unittest.main()
