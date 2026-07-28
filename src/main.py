"""Command-line entry point for VideoText."""

import argparse
from pathlib import Path
import sys
from typing import Callable, Optional

from batch_processing import (
    BatchProcessingRequest,
    BatchProgress,
    format_batch_summary,
    process_batch,
    videos_in_folder,
)
from menu import CliProcessingMode, select_cli_mode, select_processing_mode
from os_integration import default_cli_output_root, resolve_cli_output_root
from processing_service import (
    ProcessingMode,
    ProcessingProgress,
    ProcessingRequest,
    ProcessingResult,
    format_duration,
    format_processing_summary,
    process_request,
)


def process_video(
    video_path: str,
    output_directory: Path,
    formats: list[str],
    progress_callback: Optional[Callable[[ProcessingProgress], None]] = None,
) -> ProcessingResult:
    """Run the existing full-video workflow through the shared service."""

    return process_request(
        ProcessingRequest(
            mode=ProcessingMode.FULL_VIDEO,
            source_path=video_path,
            output_directory=Path(output_directory),
            formats=formats,
            progress_callback=progress_callback,
        )
    )


EXPORT_FORMATS = ("markdown", "csv", "excel")
FORMAT_SELECTIONS = {
    "1": "markdown",
    "2": "csv",
    "3": "excel",
    **{name: name for name in EXPORT_FORMATS},
}


def normalize_export_formats(selection: str) -> list[str]:
    """Convert CLI numbers or names into canonical exporter format names."""

    entered = selection.strip().lower()
    selections = [item.strip() for item in entered.split(",") if item.strip()]

    if not selections:
        return list(EXPORT_FORMATS)

    normalized: set[str] = set()
    invalid: list[str] = []

    for selection_name in selections:
        if selection_name == "all":
            normalized.update(EXPORT_FORMATS)
        elif selection_name in FORMAT_SELECTIONS:
            normalized.add(FORMAT_SELECTIONS[selection_name])
        else:
            invalid.append(selection_name)

    if invalid:
        raise ValueError(f"Unsupported export format(s): {', '.join(invalid)}")

    # Canonical ordering makes the confirmation and submitted request stable.
    return [name for name in EXPORT_FORMATS if name in normalized]


def _prompt_formats() -> list[str]:
    """Prompt for the three supported exporter formats."""

    print("Export formats:")
    print("1. Markdown")
    print("2. CSV")
    print("3. Excel")
    entered = input("Select formats [1,2,3]: ")
    return normalize_export_formats(entered)


def build_cli_argument_parser() -> argparse.ArgumentParser:
    """Build the small argument parser shared by interactive CLI modes."""

    parser = argparse.ArgumentParser(description="Run VideoText processing.")
    parser.add_argument(
        "--output",
        metavar="PATH",
        help="Output root. Defaults to your Documents/VideoText Output folder.",
    )
    return parser


def _prompt_output_root(explicit_output_root: Path | None = None) -> Path:
    """Use an explicit CLI path or prompt with the safe per-user default."""

    if explicit_output_root is not None:
        return explicit_output_root

    default_root = default_cli_output_root()
    entered_path = input(f"Output root [{default_root}]: ").strip()
    return resolve_cli_output_root(entered_path or None)


def _prompt_request(
    mode: ProcessingMode | None = None,
    output_root: Path | None = None,
) -> ProcessingRequest:
    """Collect a full or resumed request for the existing CLI workflow."""

    mode = mode or select_processing_mode()
    if mode is ProcessingMode.FULL_VIDEO:
        source_prompt = "Video: "
    else:
        source_prompt = "Checkpoint file or prior run folder: "

    source_path = input(source_prompt).strip()
    return ProcessingRequest(
        mode=mode,
        source_path=source_path,
        output_directory=_prompt_output_root(output_root),
        formats=_prompt_formats(),
        progress_callback=_print_progress,
    )


def _print_progress(progress: ProcessingProgress) -> None:
    """Display shared pipeline progress without calculating timing locally."""

    message = progress.message
    if progress.current is not None and progress.total is not None:
        item_label = "frame " if progress.stage in {"ocr", "reading_order"} else ""
        message += f" — {item_label}{progress.current} of {progress.total}"

    message += f" | elapsed {format_duration(progress.elapsed_seconds)}"
    if progress.estimated_remaining_seconds is not None:
        message += (
            " | remaining "
            f"{format_duration(progress.estimated_remaining_seconds)}"
        )

    print(message)


def _prompt_batch_request(
    mode: CliProcessingMode,
    output_root: Path | None = None,
) -> BatchProcessingRequest:
    """Collect batch paths, one output root, and one set of export formats."""

    if mode is CliProcessingMode.BATCH_FILES:
        print("Enter video paths one per line. Submit a blank line when finished.")
        source_paths: list[str] = []
        while True:
            source_path = input("Video path: ").strip()
            if not source_path:
                break
            source_paths.append(source_path)
    else:
        folder = input("Video folder: ").strip()
        source_paths = videos_in_folder(folder)

    if not source_paths:
        raise ValueError("Batch processing requires at least one video file.")

    return BatchProcessingRequest(
        source_paths=source_paths,
        output_directory=_prompt_output_root(output_root),
        formats=_prompt_formats(),
        progress_callback=_print_batch_progress,
    )


def _print_batch_progress(event: BatchProgress) -> None:
    """Display shared item and stage progress without independent timing."""

    prefix = (
        f"Processing video {event.current_item} of {event.total_items}: "
        f"{event.filename}"
    )
    print(prefix)
    if event.progress is not None:
        _print_progress(event.progress)


def main(arguments: list[str] | None = None):
    """Run the shared processing service from the command line."""

    options = build_cli_argument_parser().parse_args(arguments or [])
    explicit_output_root = (
        resolve_cli_output_root(options.output)
        if options.output is not None
        else None
    )
    mode = select_cli_mode()

    if isinstance(mode, CliProcessingMode):
        request = _prompt_batch_request(mode, explicit_output_root)
        print(f"Selected formats: {', '.join(request.formats)}")
        result = process_batch(request)
        print()
        print(format_batch_summary(result))
        return result

    request = _prompt_request(mode, explicit_output_root)
    print(f"Selected formats: {', '.join(request.formats)}")
    result = process_request(request)
    print()
    print(format_processing_summary(result))

    return result.presentation


if __name__ == "__main__":
    main(sys.argv[1:])
