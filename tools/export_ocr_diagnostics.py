"""Run VideoText with optional evidence exports for OCR diagnosis.

Use --video for a normal supported local/HTTP source, or --checkpoint with a
matching resume mode. Diagnostics are developer artifacts and may contain
sensitive frame images and extracted text.
"""

from __future__ import annotations

import argparse
from pathlib import Path
import sys


PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from ocr_diagnostics import DiagnosticError, DiagnosticOptions  # noqa: E402
from processing_service import (  # noqa: E402
    ProcessingMode,
    ProcessingRequest,
    process_request,
)


def _integer_set(value: str) -> frozenset[int]:
    try:
        parsed = frozenset(int(item.strip()) for item in value.split(",") if item.strip())
    except ValueError as error:
        raise argparse.ArgumentTypeError("Frame and slide selections must be comma-separated integers.") from error
    if not parsed:
        raise argparse.ArgumentTypeError("Provide at least one frame or slide number.")
    return parsed


def main() -> int:
    parser = argparse.ArgumentParser(description="Export VideoText OCR diagnostic evidence.")
    source_group = parser.add_mutually_exclusive_group(required=True)
    source_group.add_argument("--video", help="Local video path or supported HTTP/HTTPS video URL")
    source_group.add_argument("--checkpoint", help="Existing VideoText checkpoint file or run folder")
    parser.add_argument("--mode", choices=[mode.value for mode in ProcessingMode if mode is not ProcessingMode.FULL_VIDEO], help="Required when using --checkpoint")
    parser.add_argument("--output-dir", required=True, type=Path, help="Diagnostic output directory")
    selection_group = parser.add_mutually_exclusive_group(required=True)
    selection_group.add_argument("--all-candidates", action="store_true", help="Export every candidate frame")
    selection_group.add_argument("--frames", type=_integer_set, help="Comma-separated candidate frame indices")
    selection_group.add_argument("--slides", type=_integer_set, help="Comma-separated final slide numbers")
    parser.add_argument("--low-confidence-threshold", type=float, default=0.80)
    parser.add_argument("--overwrite", action="store_true", help="Allow writing into an existing diagnostic directory")
    parser.add_argument("--strict", action="store_true", help="Fail for unavailable selections or diagnostic writes")
    arguments = parser.parse_args()
    if arguments.checkpoint and not arguments.mode:
        parser.error("--mode is required with --checkpoint")
    if arguments.video and arguments.mode:
        parser.error("--mode can only be used with --checkpoint")

    mode = ProcessingMode.FULL_VIDEO if arguments.video else ProcessingMode(arguments.mode)
    source_path = arguments.video or arguments.checkpoint
    options = DiagnosticOptions(
        output_directory=arguments.output_dir,
        all_candidate_frames=arguments.all_candidates,
        frame_indices=arguments.frames or frozenset(),
        slide_numbers=arguments.slides or frozenset(),
        low_confidence_threshold=arguments.low_confidence_threshold,
        overwrite=arguments.overwrite,
        strict=arguments.strict,
    )
    try:
        result = process_request(ProcessingRequest(
            mode=mode,
            source_path=source_path,
            # Keep normal VideoText artifacts beside, not inside, the
            # diagnostic destination so overwrite protection remains useful.
            output_directory=arguments.output_dir.parent / f"{arguments.output_dir.name}-run",
            formats=["markdown"],
            diagnostic_options=options,
        ))
    except (DiagnosticError, ValueError, OSError) as error:
        print(f"Diagnostic export failed: {error}", file=sys.stderr)
        return 2
    print(f"Diagnostics complete: {arguments.output_dir}")
    print(f"Candidate frames: {result.frame_count}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
