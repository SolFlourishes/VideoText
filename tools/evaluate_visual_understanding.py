"""Evaluate one explicitly supplied local visual capability pack."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys
from time import monotonic


PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from app_info import APP_RELEASE  # noqa: E402
from local_visual_runtime import LocalVisualRuntime  # noqa: E402
from local_visual_understanding_provider import LocalVisualUnderstandingProvider  # noqa: E402
from visual_capability_pack import (  # noqa: E402
    VISUAL_PACK_MANIFEST_FILENAME,
    VisualPackReadinessState,
    check_visual_capability_pack_readiness,
    load_visual_capability_pack_manifest,
)
from visual_understanding_evaluation import (  # noqa: E402
    load_visual_evaluation_cases,
    run_visual_evaluation,
    write_visual_evaluation_outputs,
)
from visual_understanding_pipeline import DEFAULT_VISUAL_PROMPT_SCHEMA_REVISION  # noqa: E402


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run the local VideoText visual-understanding evaluation corpus.",
    )
    parser.add_argument("--pack", required=True, type=Path, help="Path to the explicit pack directory or manifest JSON.")
    parser.add_argument("--cases", required=True, type=Path, help="Directory containing evaluation case JSON and PNG files.")
    parser.add_argument("--output", required=True, type=Path, help="Dedicated evaluation output directory.")
    parser.add_argument(
        "--application-version", default=APP_RELEASE,
        help="Development-only pack preflight override; does not change APP_RELEASE.",
    )
    parser.add_argument(
        "--startup-timeout", type=float, default=300.0,
        help="Evaluation-only local runtime startup limit in seconds (default: 300).",
    )
    parser.add_argument(
        "--maximum-image-dimension", type=int, default=1536,
        help="Bound the submitted image's longest edge (default: 1536; source evidence is unchanged).",
    )
    parser.add_argument(
        "--request-timeout", type=float, default=150.0,
        help="Per-case local request limit in seconds (default: 150).",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    arguments = build_parser().parse_args(argv)
    runtime = None
    try:
        cases = load_visual_evaluation_cases(arguments.cases)
        manifest = arguments.pack / VISUAL_PACK_MANIFEST_FILENAME if arguments.pack.is_dir() else arguments.pack
        pack = load_visual_capability_pack_manifest(
            manifest, application_version=arguments.application_version,
        )
        readiness = check_visual_capability_pack_readiness(
            pack, requested_prompt_schema=DEFAULT_VISUAL_PROMPT_SCHEMA_REVISION,
            verify_hashes=True, application_version=arguments.application_version,
        )
        if readiness.state is VisualPackReadinessState.NOT_READY:
            print("Local visual capability pack failed readiness verification.", file=sys.stderr)
            return 2
        runtime = LocalVisualRuntime(pack, readiness, startup_timeout=arguments.startup_timeout)
        startup_started = monotonic()
        runtime.start()
        runtime.wait_until_ready()
        startup_seconds = monotonic() - startup_started
        provider = LocalVisualUnderstandingProvider(runtime, request_timeout=arguments.request_timeout)
        status = runtime.status
        evaluation = run_visual_evaluation(
            cases, provider, startup_seconds=startup_seconds,
            runtime_metadata={
                "pack_id": status.pack_id, "pack_version": status.pack_version,
                "runtime_family": status.runtime_family, "runtime_version": status.runtime_version,
                "backend_declared": status.backend_declared,
                "runtime_confirmed_metadata": dict(status.runtime_metadata),
                "application_version_used_for_preflight": arguments.application_version,
            },
            maximum_image_dimension=arguments.maximum_image_dimension,
        )
        json_path, markdown_path = write_visual_evaluation_outputs(evaluation, arguments.output)
        print(f"Evaluation JSON: {json_path}")
        print(f"Evaluation report: {markdown_path}")
        return 0 if evaluation["aggregate"]["failed_responses"] == 0 else 1
    except Exception as error:
        print(f"Evaluation failed safely: {type(error).__name__}: {error}", file=sys.stderr)
        return 2
    finally:
        if runtime is not None:
            try:
                runtime.stop()
            except Exception:
                pass


if __name__ == "__main__":
    raise SystemExit(main())
