"""Shared full and resumed processing entry point for VideoText."""

from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Callable, Optional
from time import monotonic

from cache_manager import load_cache, save_cache
from export_manager import export_all
from models import Presentation, ensure_raw_ocr_results
from ocr_diagnostics import DiagnosticOptions, OCRDiagnosticsWriter
from run_workspace import (
    create_replay_run_directory,
    create_run_directory,
    sanitize_video_stem,
)
from video_source import resolve_video_source


# Keep optional video/OCR dependencies out of module import time.  This lets
# the GUI and command-line menus open normally even before processing starts.
def open_video(video_path: str):
    from video_reader import open_video as implementation
    return implementation(video_path)


def analyze_video(video, fps, progress_callback=None, total_frames=None):
    from frame_analyzer import analyze_video as implementation
    return implementation(
        video,
        fps,
        progress_callback=progress_callback,
        total_frames=total_frames,
    )


def get_video_frame_count(video):
    from video_reader import get_frame_count as implementation
    return implementation(video)


def save_candidate_frames(candidate_frames, output_folder):
    from frame_saver import save_candidate_frames as implementation
    return implementation(candidate_frames, output_folder)


def perform_ocr(candidate_frames, progress_callback=None):
    from ocr_engine import perform_ocr as implementation
    return implementation(candidate_frames, progress_callback=progress_callback)


def reconstruct_reading_order(candidate_frames, progress_callback=None):
    from reading_order import reconstruct_reading_order as implementation
    return implementation(candidate_frames, progress_callback=progress_callback)


def consolidate_slides(candidate_frames):
    from slide_consolidator import consolidate_slides as implementation
    return implementation(candidate_frames)


class ProcessingMode(Enum):
    """The pipeline checkpoint from which processing starts."""

    FULL_VIDEO = "full_video"
    CANDIDATE_FRAMES = "candidate_frames"
    OCR_RESULTS = "ocr_results"
    READING_ORDER = "reading_order"


PHASE_STAGES = {
    ProcessingMode.FULL_VIDEO: (
        "frame_selection",
        "ocr",
        "reading_order",
        "consolidation",
        "export",
    ),
    ProcessingMode.CANDIDATE_FRAMES: (
        "ocr",
        "reading_order",
        "consolidation",
        "export",
    ),
    ProcessingMode.OCR_RESULTS: (
        "reading_order",
        "consolidation",
        "export",
    ),
    ProcessingMode.READING_ORDER: (
        "consolidation",
        "export",
    ),
}


CHECKPOINT_NAMES = {
    ProcessingMode.CANDIDATE_FRAMES: "candidate_frames.pkl",
    ProcessingMode.OCR_RESULTS: "ocr_results.pkl",
    ProcessingMode.READING_ORDER: "reading_order.pkl",
}

PROGRESS_MINIMUM_FRAME_COUNT = 500
PROGRESS_MINIMUM_ELAPSED_SECONDS = 5.0
OCR_ETA_MINIMUM_ITEM_COUNT = 5
OCR_ETA_MINIMUM_ELAPSED_SECONDS = 10.0
ETA_POLICIES = {
    "ocr": (OCR_ETA_MINIMUM_ITEM_COUNT, OCR_ETA_MINIMUM_ELAPSED_SECONDS),
}


@dataclass(frozen=True)
class ProcessingProgress:
    """One shared pipeline progress update for CLI and GUI consumers."""

    stage: str
    message: str
    current: int | None
    total: int | None
    elapsed_seconds: float
    estimated_remaining_seconds: float | None
    percentage: float | None = None
    step_current: int | None = None
    step_total: int | None = None


def format_duration(seconds: float) -> str:
    """Format a non-negative duration compactly for terminal and GUI display."""

    total_seconds = max(0, int(seconds))
    hours, remainder = divmod(total_seconds, 3600)
    minutes, seconds = divmod(remainder, 60)

    if hours:
        return f"{hours}h {minutes:02d}m"
    if minutes:
        return f"{minutes}m {seconds:02d}s"
    return f"{seconds} seconds"


def format_bytes(byte_count: int) -> str:
    """Format a non-negative byte count compactly for shared progress views."""

    value = max(0, byte_count)
    units = ("bytes", "KB", "MB", "GB")
    for index, unit in enumerate(units):
        if value < 1024 or index == len(units) - 1:
            return (
                f"{int(value)} {unit}"
                if unit == "bytes"
                else f"{value:.1f} {unit}"
            )
        value /= 1024
    return f"{value:.1f} TB"


class ProgressReporter:
    """Own stage timing and ETA calculation for a single processing request."""

    def __init__(
        self,
        callback: Optional[Callable[[ProcessingProgress], None]],
        phase_stages: tuple[str, ...] = (),
        clock: Callable[[], float] = monotonic,
    ) -> None:
        self.callback = callback
        self.clock = clock
        self.pipeline_started = clock()
        self.stage_started = self.pipeline_started
        self.total_elapsed_seconds = 0.0
        self.phase_steps = {
            stage: index
            for index, stage in enumerate(phase_stages, start=1)
        }
        self.phase_total = len(phase_stages)

    def stage(self, stage: str, message: str) -> None:
        self.stage_started = self.clock()
        self._emit(stage, message, None, None)

    def item(self, stage: str, message: str, current: int, total: int) -> None:
        eta_minimum_current, eta_minimum_elapsed = ETA_POLICIES.get(
            stage,
            (3, 0.0),
        )
        self._emit(
            stage,
            message,
            current,
            total,
            eta_minimum_current=eta_minimum_current,
            eta_minimum_elapsed=eta_minimum_elapsed,
        )

    def frame_selection(self, current: int, total: int | None) -> None:
        """Emit frame-analysis progress with the conservative frame ETA rule."""
        percentage = None
        if total is not None and total > 0:
            percentage = min(100.0, (current / total) * 100)

        self._emit(
            "frame_selection",
            "Selecting stable frames",
            current,
            total,
            percentage=percentage,
            eta_minimum_current=PROGRESS_MINIMUM_FRAME_COUNT,
            eta_minimum_elapsed=PROGRESS_MINIMUM_ELAPSED_SECONDS,
        )

    def download(self, current: int, total: int | None) -> None:
        """Emit pre-pipeline download progress as step zero of this run."""

        percentage = None
        if total is not None and total > 0:
            percentage = min(100.0, (current / total) * 100)
        self._emit(
            "download",
            "Downloading video",
            current,
            total,
            percentage=percentage,
            eta_minimum_current=3,
            step_current=0,
            step_total=self.phase_total,
        )

    def complete(self) -> None:
        elapsed = max(0.0, self.clock() - self.pipeline_started)
        self.total_elapsed_seconds = elapsed
        self._emit("complete", "Complete", None, None, elapsed=elapsed)

    def _emit(
        self,
        stage: str,
        message: str,
        current: int | None,
        total: int | None,
        elapsed: float | None = None,
        percentage: float | None = None,
        eta_minimum_current: int = 3,
        eta_minimum_elapsed: float = 0.0,
        step_current: int | None = None,
        step_total: int | None = None,
    ) -> None:
        if self.callback is None:
            return

        elapsed_seconds = (
            max(0.0, self.clock() - self.stage_started)
            if elapsed is None
            else elapsed
        )
        estimated_remaining_seconds = None

        if (
            current is not None
            and total is not None
            and current >= eta_minimum_current
            and elapsed_seconds >= eta_minimum_elapsed
            and total > 0
        ):
            remaining = max(0, total - current)
            estimated_remaining_seconds = max(
                0.0,
                (elapsed_seconds / current) * remaining,
            )

        self.callback(ProcessingProgress(
            stage=stage,
            message=message,
            current=current,
            total=total,
            elapsed_seconds=elapsed_seconds,
            estimated_remaining_seconds=estimated_remaining_seconds,
            percentage=percentage,
            step_current=(
                self.phase_steps.get(stage)
                if step_current is None else step_current
            ),
            step_total=(
                self.phase_total if stage in self.phase_steps else None
                if step_total is None else step_total
            ),
        ))


@dataclass(frozen=True)
class ProcessingRequest:
    """All inputs required for one full or resumed processing run."""

    mode: ProcessingMode
    source_path: str
    output_directory: Path
    formats: list[str]
    progress_callback: Optional[Callable[[ProcessingProgress], None]] = None
    diagnostic_options: DiagnosticOptions | None = None


@dataclass(frozen=True)
class ProcessingResult:
    """The reconstructed document and files produced by one processing run."""

    presentation: Presentation
    run_directory: Path
    exported_paths: dict[str, str]
    mode: ProcessingMode
    source_path: str
    resolved_checkpoint_path: Path | None
    frame_count: int | None
    elapsed_seconds: float


MODE_LABELS = {
    ProcessingMode.FULL_VIDEO: "Full video",
    ProcessingMode.CANDIDATE_FRAMES: "Candidate frames cache",
    ProcessingMode.OCR_RESULTS: "OCR results cache",
    ProcessingMode.READING_ORDER: "Reading-order cache",
}
FRAME_COUNT_LABELS = {
    ProcessingMode.FULL_VIDEO: "Candidate frames processed",
    ProcessingMode.CANDIDATE_FRAMES: "Candidate frames loaded",
    ProcessingMode.OCR_RESULTS: "OCR frames processed",
    ProcessingMode.READING_ORDER: "Reading-order frames loaded",
}
EXPORT_LABELS = {
    "markdown": "Markdown",
    "csv": "CSV",
    "excel": "Excel",
}


def format_processing_summary(result: ProcessingResult) -> str:
    """Format one shared, user-facing successful-run summary."""

    lines = ["Processing Complete", "", f"Mode: {MODE_LABELS[result.mode]}"]

    if result.source_path:
        source_name = Path(result.source_path.split("?", maxsplit=1)[0]).name
        lines.append(f"Video: {source_name or result.source_path}")
        if result.mode is ProcessingMode.FULL_VIDEO:
            origin = "Downloaded HTTP/HTTPS video" if "://" in result.source_path else "Local file"
            lines.append(f"Source type: {origin}")
        lines.append(f"Source: {result.source_path}")
    if result.resolved_checkpoint_path is not None:
        lines.append(f"Resolved checkpoint: {result.resolved_checkpoint_path}")
    if result.frame_count is not None:
        lines.append(f"{FRAME_COUNT_LABELS[result.mode]}: {result.frame_count}")

    lines.extend([
        f"Slides created: {len(result.presentation.slides)}",
        f"Elapsed time: {format_duration(result.elapsed_seconds)}",
        f"Output folder: {result.run_directory}",
        "",
        "Exports:",
    ])

    for format_name, path in result.exported_paths.items():
        label = EXPORT_LABELS.get(format_name, format_name.title())
        lines.append(f"- {label}: {path}")

    return "\n".join(lines)


class CheckpointValidationError(ValueError):
    """Raised when a selected resume source is not the expected checkpoint."""


class CheckpointLoadError(ValueError):
    """Raised when an existing checkpoint cannot be unpickled."""


def _mode_label(mode: ProcessingMode) -> str:
    return mode.value.replace("_", " ")


def resolve_checkpoint_path(mode: ProcessingMode, source_path: str) -> Path:
    """Resolve and validate a checkpoint file or prior run directory."""

    expected_name = CHECKPOINT_NAMES.get(mode)
    if expected_name is None:
        raise CheckpointValidationError(
            f"Mode '{_mode_label(mode)}' does not use a checkpoint."
        )

    source = Path(source_path)
    is_run_directory = source.is_dir() or (
        not source.exists() and source.suffix.lower() != ".pkl"
    )
    checked_path = source / "cache" / expected_name if is_run_directory else source

    if checked_path.name != expected_name:
        raise CheckpointValidationError(
            f"Resume mode '{_mode_label(mode)}' expected checkpoint "
            f"'{expected_name}'. Checked path: {checked_path}."
        )

    if not checked_path.is_file():
        raise CheckpointValidationError(
            f"Resume mode '{_mode_label(mode)}' expected checkpoint "
            f"'{expected_name}'. Checked path: {checked_path}. "
            "The file is absent."
        )

    return checked_path


def _load_checkpoint(mode: ProcessingMode, source_path: str):
    """Load a validated checkpoint without changing its source file."""

    checkpoint_path = resolve_checkpoint_path(mode, source_path)

    try:
        return checkpoint_path, load_cache(checkpoint_path)
    except Exception as error:
        expected_name = CHECKPOINT_NAMES[mode]
        raise CheckpointLoadError(
            f"Resume mode '{_mode_label(mode)}' expected checkpoint "
            f"'{expected_name}'. Checked path: {checkpoint_path}. "
            f"The file could not be loaded: {type(error).__name__}: {error}"
        ) from error


def _source_run_stem(checkpoint_path: Path) -> str:
    """Derive a readable output name from the source run containing a cache."""

    source_run = (
        checkpoint_path.parent.parent
        if checkpoint_path.parent.name.lower() == "cache"
        else checkpoint_path.parent
    )
    return sanitize_video_stem(source_run.name)


def _create_presentation(candidate_frames, metadata: dict[str, object]) -> Presentation:
    slides = consolidate_slides(candidate_frames)
    return Presentation(
        metadata=metadata,
        slides=slides,
        statistics={
            "candidate_frames": len(candidate_frames),
            "slides_detected": len(slides),
        },
    )


def _normalize_raw_ocr_evidence(candidate_frames) -> None:
    """Adapt loaded checkpoint frames before later stages replace working OCR."""

    for frame in candidate_frames:
        ensure_raw_ocr_results(frame)


def _finish_run(
    candidate_frames,
    request: ProcessingRequest,
    run_directory: Path,
    output_stem: str,
    metadata: dict[str, object],
    reporter: ProgressReporter,
    diagnostics: OCRDiagnosticsWriter | None = None,
) -> ProcessingResult:
    reporter.stage("consolidation", "Consolidating slides")
    presentation = _create_presentation(candidate_frames, metadata)
    if diagnostics is not None:
        diagnostics.capture_slides(presentation.slides)
        try:
            diagnostics.write(run_directory)
        except Exception as error:
            message = f"OCR diagnostics were not written: {type(error).__name__}: {error}"
            diagnostics.failures.append(message)
            print(message)
            if diagnostics.options.strict:
                raise

    reporter.stage("export", "Exporting files")
    exported_paths = export_all(
        presentation,
        run_directory,
        request.formats,
        output_stem,
        progress_callback=lambda current, total: reporter.item(
            "export",
            "Exporting files",
            current,
            total,
        ),
        candidate_frames=candidate_frames,
    )

    reporter.complete()
    return ProcessingResult(
        presentation=presentation,
        run_directory=run_directory,
        exported_paths=exported_paths,
        mode=request.mode,
        source_path=request.source_path,
        resolved_checkpoint_path=metadata.get("resolved_checkpoint_path"),
        frame_count=len(candidate_frames),
        elapsed_seconds=reporter.total_elapsed_seconds,
    )


def process_request(request: ProcessingRequest) -> ProcessingResult:
    """Run precisely the pipeline stages required by a processing request."""

    output_root = Path(request.output_directory)
    reporter = ProgressReporter(
        request.progress_callback,
        phase_stages=PHASE_STAGES[request.mode],
    )
    diagnostics = (
        OCRDiagnosticsWriter(request.diagnostic_options, request.source_path)
        if request.diagnostic_options is not None
        else None
    )

    if request.mode is ProcessingMode.FULL_VIDEO:
        resolved_source = resolve_video_source(
            request.source_path,
            progress_callback=reporter.download,
        )
        try:
            resolved_video_path = resolved_source.local_path
            reporter.stage("preparing_video", "Preparing video")
            video, fps = open_video(str(resolved_video_path))

            try:
                output_stem, run_directory = create_run_directory(
                    output_root,
                    str(resolved_video_path),
                )
                cache_directory = run_directory / "cache"

                reporter.stage("frame_selection", "Selecting stable frames")
                candidate_frames = analyze_video(
                    video,
                    fps,
                    progress_callback=reporter.frame_selection,
                    total_frames=get_video_frame_count(video),
                )
                save_candidate_frames(candidate_frames, run_directory / "candidate_frames")
                save_cache(candidate_frames, cache_directory / "candidate_frames.pkl")

                reporter.stage("ocr", "Running OCR")
                candidate_frames = perform_ocr(
                    candidate_frames,
                    progress_callback=lambda current, total: reporter.item(
                        "ocr",
                        "Running OCR",
                        current,
                        total,
                    ),
                )
                if diagnostics is not None:
                    diagnostics.capture_ocr_frames(candidate_frames)
                save_cache(candidate_frames, cache_directory / "ocr_results.pkl")

                reporter.stage("reading_order", "Determining reading order")
                candidate_frames = reconstruct_reading_order(
                    candidate_frames,
                    progress_callback=lambda current, total: reporter.item(
                        "reading_order",
                        "Reconstructing paragraphs",
                        current,
                        total,
                    ),
                )
                if diagnostics is not None:
                    diagnostics.capture_reconstructed_frames(candidate_frames)
                save_cache(candidate_frames, cache_directory / "reading_order.pkl")

                return _finish_run(
                    candidate_frames,
                    request,
                    run_directory,
                    output_stem,
                    {"video_path": str(resolved_video_path)},
                    reporter,
                    diagnostics,
                )
            finally:
                video.release()
        finally:
            resolved_source.cleanup()

    loading_message = {
        ProcessingMode.CANDIDATE_FRAMES: "Loading candidate-frames checkpoint",
        ProcessingMode.OCR_RESULTS: "Loading OCR-results checkpoint",
        ProcessingMode.READING_ORDER: "Loading reading-order checkpoint",
    }[request.mode]
    reporter.stage("checkpoint", loading_message)
    checkpoint_path, candidate_frames = _load_checkpoint(
        request.mode,
        request.source_path,
    )
    _normalize_raw_ocr_evidence(candidate_frames)
    reporter.stage("checkpoint", f"Resolved checkpoint: {checkpoint_path}")

    output_stem, run_directory = create_replay_run_directory(
        output_root,
        _source_run_stem(checkpoint_path),
    )
    cache_directory = run_directory / "cache"
    metadata = {
        "source_checkpoint": str(checkpoint_path),
        "processing_mode": request.mode.value,
        "resolved_checkpoint_path": checkpoint_path,
    }

    if request.mode is ProcessingMode.CANDIDATE_FRAMES:
        save_candidate_frames(candidate_frames, run_directory / "candidate_frames")
        save_cache(candidate_frames, cache_directory / "candidate_frames.pkl")

        reporter.stage("ocr", "Running OCR")
        candidate_frames = perform_ocr(
            candidate_frames,
            progress_callback=lambda current, total: reporter.item(
                "ocr", "Running OCR", current, total,
            ),
        )
        if diagnostics is not None:
            diagnostics.capture_ocr_frames(candidate_frames)
        save_cache(candidate_frames, cache_directory / "ocr_results.pkl")

        reporter.stage("reading_order", "Determining reading order")
        candidate_frames = reconstruct_reading_order(
            candidate_frames,
            progress_callback=lambda current, total: reporter.item(
                "reading_order", "Reconstructing paragraphs", current, total,
            ),
        )
        if diagnostics is not None:
            diagnostics.capture_reconstructed_frames(candidate_frames)
        save_cache(candidate_frames, cache_directory / "reading_order.pkl")

    elif request.mode is ProcessingMode.OCR_RESULTS:
        save_cache(candidate_frames, cache_directory / "ocr_results.pkl")
        if diagnostics is not None:
            diagnostics.capture_ocr_frames(candidate_frames)

        reporter.stage("reading_order", "Determining reading order")
        candidate_frames = reconstruct_reading_order(
            candidate_frames,
            progress_callback=lambda current, total: reporter.item(
                "reading_order", "Reconstructing paragraphs", current, total,
            ),
        )
        if diagnostics is not None:
            diagnostics.capture_reconstructed_frames(candidate_frames)
        save_cache(candidate_frames, cache_directory / "reading_order.pkl")

    elif request.mode is ProcessingMode.READING_ORDER:
        save_cache(candidate_frames, cache_directory / "reading_order.pkl")
        if diagnostics is not None:
            diagnostics.capture_reconstructed_frames(
                candidate_frames,
                raw_sequence_available=False,
            )

    return _finish_run(
        candidate_frames,
        request,
        run_directory,
        output_stem,
        metadata,
        reporter,
        diagnostics,
    )
