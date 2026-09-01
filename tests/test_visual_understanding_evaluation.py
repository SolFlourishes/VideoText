import contextlib
import importlib.util
import io
import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from visual_understanding_contract import (
    VisualAnalysisStatus,
    VisualAnalysisWarning,
    VisualContentType,
    VisualRelationship,
    VisualUnderstandingResult,
)
from visual_understanding_evaluation import (
    EVALUATION_RESULT_SCHEMA_VERSION,
    VisualEvaluationError,
    evaluate_visual_case,
    load_visual_evaluation_case,
    load_visual_evaluation_cases,
    run_visual_evaluation,
    write_visual_evaluation_outputs,
)


FIXTURES = Path(__file__).parent / "fixtures" / "visual_evaluation"


class FakeProvider:
    provider_id = "fake-local"

    def __init__(self, outcomes=None):
        self.outcomes = list(outcomes or [])
        self.requests = []

    def analyze(self, request):
        self.requests.append(request)
        outcome = self.outcomes.pop(0) if self.outcomes else {}
        if isinstance(outcome, Exception):
            raise outcome
        if "failure" in outcome:
            return VisualUnderstandingResult(
                request=request, status=VisualAnalysisStatus.FAILURE,
                provider_id=self.provider_id, error=outcome["failure"],
                provider_metadata={"pack_id": "test-pack"},
            )
        return VisualUnderstandingResult(
            request=request, status=VisualAnalysisStatus.SUCCESS,
            provider_id=self.provider_id, model_id="test-model",
            content_type=outcome.get("content_type", VisualContentType.CHART_OR_GRAPH),
            description=outcome.get("description", "A conservative interpretation."),
            relationships=tuple(outcome.get("relationships", ())),
            structured_details=outcome.get("details", {}),
            warnings=tuple(outcome.get("warnings", ())),
            provider_metadata={"pack_id": "test-pack", "runtime_backend": "cpu"},
        )


class StepClock:
    def __init__(self):
        self.value = 0.0

    def __call__(self):
        self.value += 0.25
        return self.value


class VisualUnderstandingEvaluationTests(unittest.TestCase):
    def setUp(self):
        self.temp = Path(tempfile.mkdtemp())

    def tearDown(self):
        shutil.rmtree(self.temp)

    def case(self, name="01-pie-chart.json"):
        return load_visual_evaluation_case(FIXTURES / name)

    def evaluate(self, cases, provider=None):
        return run_visual_evaluation(cases, provider or FakeProvider(), clock=StepClock())

    def test_repository_corpus_loads_in_filename_order(self):
        cases = load_visual_evaluation_cases(FIXTURES)
        self.assertEqual(10, len(cases))
        self.assertEqual("pie-chart", cases[0].case_id)
        self.assertEqual("ambiguous-visual", cases[-1].case_id)
        self.assertEqual({"chart", "diagram", "table", "photo", "decorative", "text", "ambiguous"}, {item.category for item in cases})

    def test_case_retains_conservative_expectation_layers(self):
        case = self.case()
        self.assertEqual(2, len(case.required_relationships))
        self.assertTrue(case.allowed_facts)
        self.assertTrue(case.prohibited_claims)
        self.assertFalse(case.human_review_required)

    def test_external_local_directory_is_supported(self):
        shutil.copytree(FIXTURES, self.temp / "external")
        self.assertEqual(10, len(load_visual_evaluation_cases(self.temp / "external")))

    def test_unknown_schema_and_fields_are_rejected(self):
        document = json.loads((FIXTURES / "01-pie-chart.json").read_text(encoding="utf-8"))
        document["schema_version"] = "future"
        target = self.temp / "case.json"
        target.write_text(json.dumps(document), encoding="utf-8")
        with self.assertRaises(VisualEvaluationError):
            load_visual_evaluation_case(target)
        document["schema_version"] = "visual-evaluation-case-v1"
        document["extra"] = True
        target.write_text(json.dumps(document), encoding="utf-8")
        with self.assertRaises(VisualEvaluationError):
            load_visual_evaluation_case(target)

    def test_traversal_image_and_non_png_are_rejected(self):
        document = json.loads((FIXTURES / "01-pie-chart.json").read_text(encoding="utf-8"))
        document["image"] = "../outside.png"
        target = self.temp / "case.json"
        target.write_text(json.dumps(document), encoding="utf-8")
        with self.assertRaises(VisualEvaluationError):
            load_visual_evaluation_case(target)

    def test_required_relationship_recovery_and_missing_detection(self):
        case = self.case()
        provider = FakeProvider([{"relationships": (case.required_relationships[0],)}])
        detail = self.evaluate((case,), provider)["cases"][0]
        self.assertEqual(1, len(detail["required_relationships_recovered"]))
        self.assertEqual(1, len(detail["required_relationships_missed"]))

    def test_allowed_content_type_match(self):
        detail = self.evaluate((self.case(),))["cases"][0]
        self.assertTrue(detail["content_type_match"])

    def test_content_type_mismatch(self):
        provider = FakeProvider([{"content_type": VisualContentType.TABLE}])
        self.assertFalse(self.evaluate((self.case(),), provider)["cases"][0]["content_type_match"])

    def test_allowed_relationship_is_not_unsupported(self):
        case = self.case()
        provider = FakeProvider([{"relationships": case.required_relationships + case.allowed_relationships}])
        self.assertFalse(self.evaluate((case,), provider)["cases"][0]["unsupported_relationships"])

    def test_unsupported_relationship_is_reported(self):
        provider = FakeProvider([{"relationships": (VisualRelationship("X", "causes", "Y"),)}])
        self.assertEqual(1, len(self.evaluate((self.case(),), provider)["cases"][0]["unsupported_relationships"]))

    def test_required_nested_details_are_checked(self):
        provider = FakeProvider([{"details": {"chart_type": "pie"}}])
        self.assertFalse(self.evaluate((self.case(),), provider)["cases"][0]["required_details_missing"])
        provider = FakeProvider([{"details": {"chart_type": "bar"}}])
        self.assertIn("chart_type", self.evaluate((self.case(),), provider)["cases"][0]["required_details_missing"])

    def test_prohibited_claim_is_detected_without_semantic_guessing(self):
        provider = FakeProvider([{"description": "Category B is 54% according to the chart."}])
        self.assertEqual(["Category B is 54%"], self.evaluate((self.case(),), provider)["cases"][0]["prohibited_claims_detected"])

    def test_ambiguous_case_warning_behavior(self):
        case = self.case("10-ambiguous-visual.json")
        warning = VisualAnalysisWarning("ambiguous", "The unlabeled meaning is uncertain.")
        provider = FakeProvider([{"content_type": VisualContentType.MIXED_OR_UNCERTAIN, "warnings": (warning,)}])
        detail = self.evaluate((case,), provider)["cases"][0]
        self.assertTrue(detail["uncertainty_warning_expected"])
        self.assertTrue(detail["uncertainty_warning_present"])

    def test_human_review_required_is_preserved(self):
        detail = self.evaluate((self.case("07-meaningful-photo.json"),))["cases"][0]
        self.assertTrue(detail["human_review_required"])

    def test_provider_failure_timeout_and_refusal_are_separate(self):
        cases = (self.case(), self.case("03-bar-chart.json"), self.case("04-process-diagram.json"))
        provider = FakeProvider([
            {"failure": "invalid_structured_output: schema mismatch"},
            {"failure": "request_timeout: local request timed out"},
            {"failure": "model_refusal: model declined"},
        ])
        result = self.evaluate(cases, provider)
        self.assertEqual(["schema_invalid", "timeout", "refusal"], [item["failure_kind"] for item in result["cases"]])
        self.assertEqual(1, result["aggregate"]["schema_invalid_responses"])
        self.assertEqual(1, result["aggregate"]["timeouts"])
        self.assertEqual(1, result["aggregate"]["refusals"])

    def test_provider_exception_is_contained_and_later_cases_continue(self):
        cases = (self.case(), self.case("03-bar-chart.json"))
        provider = FakeProvider([RuntimeError("private detail"), {}])
        result = self.evaluate(cases, provider)
        self.assertEqual(2, len(provider.requests))
        self.assertEqual("provider_failure", result["cases"][0]["failure_kind"])
        self.assertTrue(result["cases"][1]["structured_success"])
        self.assertNotIn("private detail", json.dumps(result))

    def test_multiple_cases_retain_input_order(self):
        cases = (self.case("04-process-diagram.json"), self.case())
        self.assertEqual(["process-diagram", "pie-chart"], [item["case_id"] for item in self.evaluate(cases)["cases"]])

    def test_aggregate_metrics_do_not_contain_accuracy_or_confidence(self):
        aggregate = self.evaluate((self.case(),))["aggregate"]
        self.assertNotIn("accuracy", aggregate)
        self.assertNotIn("confidence", aggregate)
        self.assertEqual(1, aggregate["requests_attempted"])

    def test_model_runtime_provenance_is_retained(self):
        result = run_visual_evaluation(
            (self.case(),), FakeProvider(), runtime_metadata={"backend_confirmed": "cpu"}, clock=StepClock(),
        )
        self.assertEqual("test-model", result["model_id"])
        self.assertEqual("test-pack", result["runtime_provenance"]["pack_id"])
        self.assertEqual("cpu", result["runtime_provenance"]["backend_confirmed"])

    def test_performance_observations_are_recorded(self):
        result = run_visual_evaluation((self.case(),), FakeProvider(), startup_seconds=1.25, clock=StepClock())
        self.assertEqual(1.25, result["performance"]["startup_seconds"])
        self.assertGreater(result["performance"]["request_seconds"][0], 0)
        self.assertGreater(result["performance"]["total_evaluation_seconds"], 0)

    def test_json_and_markdown_outputs_are_dedicated_and_inspectable(self):
        evaluation = self.evaluate((self.case(),))
        json_path, markdown_path = write_visual_evaluation_outputs(evaluation, self.temp / "output")
        document = json.loads(json_path.read_text(encoding="utf-8"))
        self.assertEqual(EVALUATION_RESULT_SCHEMA_VERSION, document["schema_version"])
        report = markdown_path.read_text(encoding="utf-8")
        self.assertIn("Human review required", report)
        self.assertIn("No combined accuracy or calibrated confidence score", report)

    def test_source_case_and_image_are_not_modified(self):
        case_path = FIXTURES / "01-pie-chart.json"
        image_path = FIXTURES / "pie-chart.png"
        before = (case_path.read_bytes(), image_path.read_bytes())
        self.evaluate((self.case(),))
        self.assertEqual(before, (case_path.read_bytes(), image_path.read_bytes()))

    def test_request_uses_exact_local_png_and_ocr_without_ocr_or_video_work(self):
        case = self.case()
        provider = FakeProvider()
        self.evaluate((case,), provider)
        request = provider.requests[0]
        self.assertEqual(case.image_path.read_bytes(), request.image_bytes)
        self.assertEqual(case.ocr_context, request.ocr_text)
        self.assertEqual("image/png", request.image_media_type)

    def test_invalid_png_content_fails_before_provider(self):
        document = json.loads((FIXTURES / "01-pie-chart.json").read_text(encoding="utf-8"))
        (self.temp / "bad.png").write_bytes(b"not png")
        document["image"] = "bad.png"
        case_path = self.temp / "case.json"
        case_path.write_text(json.dumps(document), encoding="utf-8")
        case = load_visual_evaluation_case(case_path)
        provider = FakeProvider()
        with self.assertRaises(VisualEvaluationError):
            self.evaluate((case,), provider)
        self.assertFalse(provider.requests)

    def test_no_network_or_cloud_fallback_exists_in_evaluator(self):
        source = (Path(__file__).parents[1] / "src" / "visual_understanding_evaluation.py").read_text(encoding="utf-8")
        self.assertNotIn("requests.", source)
        self.assertNotIn("openai", source.casefold())
        self.assertNotIn("http://", source)
        self.assertNotIn("https://", source)

    def test_cli_stops_runtime_when_evaluation_fails(self):
        tool_path = Path(__file__).parents[1] / "tools" / "evaluate_visual_understanding.py"
        specification = importlib.util.spec_from_file_location("evaluate_visual_understanding_tool", tool_path)
        module = importlib.util.module_from_spec(specification)
        specification.loader.exec_module(module)

        class Ready:
            state = module.VisualPackReadinessState.READY

        class Runtime:
            stopped = False

            def __init__(self, pack, readiness):
                pass

            def start(self):
                return None

            def wait_until_ready(self):
                return None

            def stop(self):
                self.stopped = True

            @property
            def status(self):
                return mock.Mock(
                    pack_id="pack", pack_version="1", runtime_family="llama.cpp",
                    runtime_version="1", backend_declared="cpu", runtime_metadata={},
                )

        holder = {}

        def runtime_factory(pack, readiness, **kwargs):
            holder["runtime"] = Runtime(pack, readiness)
            return holder["runtime"]

        with (
            mock.patch.object(module, "load_visual_evaluation_cases", return_value=(self.case(),)),
            mock.patch.object(module, "load_visual_capability_pack_manifest", return_value=object()),
            mock.patch.object(module, "check_visual_capability_pack_readiness", return_value=Ready()),
            mock.patch.object(module, "LocalVisualRuntime", side_effect=runtime_factory),
            mock.patch.object(module, "LocalVisualUnderstandingProvider", return_value=FakeProvider()),
            mock.patch.object(module, "run_visual_evaluation", side_effect=RuntimeError("test failure")),
            contextlib.redirect_stderr(io.StringIO()),
        ):
            exit_code = module.main(["--pack", "pack.json", "--cases", str(FIXTURES), "--output", str(self.temp)])
        self.assertEqual(2, exit_code)
        self.assertTrue(holder["runtime"].stopped)

    def test_cli_uses_evaluation_only_startup_timeout(self):
        tool_path = Path(__file__).parents[1] / "tools" / "evaluate_visual_understanding.py"
        specification = importlib.util.spec_from_file_location("evaluate_visual_timeout_tool", tool_path)
        module = importlib.util.module_from_spec(specification)
        specification.loader.exec_module(module)
        arguments = module.build_parser().parse_args([
            "--pack", "pack", "--cases", "cases", "--output", "output",
        ])
        self.assertEqual(300.0, arguments.startup_timeout)
        self.assertEqual("1.8.0", module.APP_RELEASE)


if __name__ == "__main__":
    unittest.main()
