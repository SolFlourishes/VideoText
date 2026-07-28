"""Shared sequential batch processing for VideoText."""

from dataclasses import dataclass, field
from datetime import datetime
import os
from pathlib import Path
from time import monotonic
from typing import Callable, Optional

from processing_service import (
    ProcessingMode,
    ProcessingProgress,
    ProcessingRequest,
    ProcessingResult,
    format_duration,
    process_request,
)


VIDEO_EXTENSIONS = (".mp4", ".avi", ".mov", ".mkv")


@dataclass(frozen=True)
class BatchProcessingRequest:
    """Inputs shared by CLI and GUI sequential full-video batches."""

    source_paths: list[str]
    output_directory: Path
    formats: list[str]
    progress_callback: Optional[Callable[["BatchProgress"], None]] = None


@dataclass(frozen=True)
class BatchProgress:
    """Identifies the active batch item and its existing stage progress."""

    current_item: int
    total_items: int
    filename: str
    progress: ProcessingProgress | None


@dataclass(frozen=True)
class BatchItemResult:
    """The independent outcome of one sequential batch item."""

    source_path: str
    success: bool
    processing_result: ProcessingResult | None
    error_message: str | None
    elapsed_seconds: float


@dataclass(frozen=True)
class BatchProcessingResult:
    """All item outcomes and the durable log for one completed batch."""

    items: list[BatchItemResult]
    log_path: Path
    elapsed_seconds: float

    @property
    def successful_items(self) -> list[BatchItemResult]:
        return [item for item in self.items if item.success]

    @property
    def failed_items(self) -> list[BatchItemResult]:
        return [item for item in self.items if not item.success]


def normalize_video_paths(paths: list[str]) -> list[str]:
    """Remove exact duplicate paths while preserving the first supplied order."""

    unique_paths: list[str] = []
    seen: set[str] = set()

    for path in paths:
        normalized = os.path.normcase(os.path.normpath(str(path)))
        if normalized not in seen:
            seen.add(normalized)
            unique_paths.append(str(path))

    return unique_paths


def videos_in_folder(folder: str | Path) -> list[str]:
    """Return supported, non-recursive video files sorted by filename."""

    directory = Path(folder)
    if not directory.is_dir():
        raise ValueError(f"Batch folder does not exist: {directory}")

    videos = sorted(
        (
            path
            for path in directory.iterdir()
            if path.is_file() and path.suffix.lower() in VIDEO_EXTENSIONS
        ),
        key=lambda path: path.name.lower(),
    )

    if not videos:
        raise ValueError(
            f"No supported video files were found in: {directory}"
        )

    return [str(path) for path in videos]


def _create_batch_log_path(output_directory: Path) -> Path:
    output_directory.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y-%m-%d_%H%M")
    base_name = f"VideoText_batch_{timestamp}"
    suffix = 1

    while True:
        name = base_name if suffix == 1 else f"{base_name}_{suffix}"
        path = output_directory / f"{name}.log"
        if not path.exists():
            return path
        suffix += 1


def _append_log(path: Path, lines: list[str]) -> None:
    with path.open("a", encoding="utf-8") as log:
        log.write("\n".join(lines) + "\n")


def _notify(
    request: BatchProcessingRequest,
    current_item: int,
    filename: str,
    progress: ProcessingProgress | None,
) -> None:
    if request.progress_callback is not None:
        request.progress_callback(BatchProgress(
            current_item=current_item,
            total_items=len(request.source_paths),
            filename=filename,
            progress=progress,
        ))


def _log_item(path: Path, item: BatchItemResult) -> None:
    lines = [
        "",
        f"Video: {item.source_path}",
        f"Elapsed: {format_duration(item.elapsed_seconds)}",
    ]

    if item.success and item.processing_result is not None:
        lines.extend([
            "Status: Success",
            f"Output workspace: {item.processing_result.run_directory}",
        ])
        for format_name, export_path in item.processing_result.exported_paths.items():
            lines.append(f"Export {format_name}: {export_path}")
    else:
        lines.extend([
            "Status: Failed",
            f"Error: {item.error_message}",
        ])

    _append_log(path, lines)


def process_batch(request: BatchProcessingRequest) -> BatchProcessingResult:
    """Process full-video items sequentially, retaining failures and progress."""

    source_paths = normalize_video_paths(request.source_paths)
    if not source_paths:
        raise ValueError("Batch processing requires at least one video file.")

    # Preserve normalized first-occurrence order throughout the batch.
    request = BatchProcessingRequest(
        source_paths=source_paths,
        output_directory=Path(request.output_directory),
        formats=list(request.formats),
        progress_callback=request.progress_callback,
    )
    log_path = _create_batch_log_path(request.output_directory)
    started_at = datetime.now().strftime("%Y-%m-%d %H:%M")
    batch_started = monotonic()
    _append_log(log_path, [
        "VideoText Batch Processing",
        f"Batch start: {started_at}",
        f"Output root: {request.output_directory}",
        f"Formats: {', '.join(request.formats)}",
        f"Total videos: {len(request.source_paths)}",
    ])

    items: list[BatchItemResult] = []

    for index, source_path in enumerate(request.source_paths, start=1):
        filename = Path(source_path).name
        item_started = monotonic()
        _notify(request, index, filename, None)

        try:
            result = process_request(ProcessingRequest(
                mode=ProcessingMode.FULL_VIDEO,
                source_path=source_path,
                output_directory=request.output_directory,
                formats=request.formats,
                progress_callback=lambda progress, item_index=index, item_name=filename: _notify(
                    request,
                    item_index,
                    item_name,
                    progress,
                ),
            ))
            item = BatchItemResult(
                source_path=source_path,
                success=True,
                processing_result=result,
                error_message=None,
                elapsed_seconds=max(0.0, monotonic() - item_started),
            )
        except Exception as error:
            item = BatchItemResult(
                source_path=source_path,
                success=False,
                processing_result=None,
                error_message=f"{type(error).__name__}: {error}",
                elapsed_seconds=max(0.0, monotonic() - item_started),
            )

        items.append(item)
        _log_item(log_path, item)

    elapsed_seconds = max(0.0, monotonic() - batch_started)
    completed_at = datetime.now().strftime("%Y-%m-%d %H:%M")
    _append_log(log_path, [
        "",
        f"Batch completion: {completed_at}",
        f"Completed: {sum(item.success for item in items)}",
        f"Failed: {sum(not item.success for item in items)}",
        f"Total elapsed: {format_duration(elapsed_seconds)}",
    ])

    return BatchProcessingResult(items, log_path, elapsed_seconds)


def format_batch_summary(result: BatchProcessingResult) -> str:
    """Format a shared, user-facing batch completion summary."""

    lines = [
        "Batch Processing Complete",
        "",
        f"Videos selected: {len(result.items)}",
        f"Completed: {len(result.successful_items)}",
        f"Failed: {len(result.failed_items)}",
        f"Total elapsed: {format_duration(result.elapsed_seconds)}",
        f"Batch log: {result.log_path}",
    ]

    if result.successful_items:
        lines.extend(("", "Successful:"))
        lines.extend(f"- {Path(item.source_path).name}" for item in result.successful_items)
    if result.failed_items:
        lines.extend(("", "Failed:"))
        for item in result.failed_items:
            lines.extend((
                f"- {Path(item.source_path).name}",
                f"  {item.error_message}",
            ))

    return "\n".join(lines)
