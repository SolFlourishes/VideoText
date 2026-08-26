"""Headless preparation for translating trusted completed VideoText results."""

from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
from typing import Callable, Iterable

from models import Presentation
from processing_service import (
    CheckpointLoadError,
    CheckpointValidationError,
    ProcessingMode,
    reconstruct_presentation_from_reading_order,
    resolve_checkpoint_path,
)
from translation_application import (
    TranslationApplicationResult,
    TranslationApplicationSource,
    run_translation_job,
)
from translation_contract import TranslationProvider
from translation_job import TranslationOutputGrouping, TranslationSourceItem


@dataclass(frozen=True)
class ValidExistingResult:
    """One selected result reconstructed into ready translation evidence."""

    selected_path: Path
    resolved_checkpoint_path: Path
    source_name: str
    presentation: Presentation
    translation_source: TranslationApplicationSource


@dataclass(frozen=True)
class InvalidExistingResult:
    """One selected path that could not provide trusted reading-order evidence."""

    selected_path: Path
    error_type: str
    message: str


@dataclass(frozen=True)
class DuplicateExistingResult:
    """One later selection resolving to an already retained checkpoint."""

    selected_path: Path
    duplicate_of: Path
    resolved_checkpoint_path: Path


@dataclass(frozen=True)
class ExistingResultsTranslationPreparation:
    """Ordered validation results and inputs ready for later translation."""

    valid_results: tuple[ValidExistingResult, ...]
    invalid_results: tuple[InvalidExistingResult, ...]
    duplicate_results: tuple[DuplicateExistingResult, ...]
    translation_sources: tuple[TranslationApplicationSource, ...]
    output_workspace: Path | None

    @property
    def has_valid_sources(self) -> bool:
        return bool(self.valid_results)


def _canonical_key(path: Path) -> str:
    return os.path.normcase(str(path.resolve()))


def _source_run_directory(checkpoint_path: Path) -> Path:
    return (
        checkpoint_path.parent.parent
        if checkpoint_path.parent.name.casefold() == "cache"
        else checkpoint_path.parent
    )


def _is_within(path: Path, directory: Path) -> bool:
    try:
        path.relative_to(directory)
    except ValueError:
        return False
    return True


def _create_output_workspace(output_root: str | Path, source_runs: Iterable[Path]) -> Path:
    root = Path(output_root).resolve()
    source_directories = tuple(directory.resolve() for directory in source_runs)
    if any(_is_within(root, directory) for directory in source_directories):
        raise ValueError("Output root must not be inside a selected completed result.")

    root.mkdir(parents=True, exist_ok=True)
    suffix = 1
    while True:
        name = "translation-existing-results" if suffix == 1 else f"translation-existing-results_{suffix}"
        workspace = root / name
        try:
            workspace.mkdir()
            return workspace
        except FileExistsError:
            suffix += 1


def prepare_existing_results_translation(
    selected_paths: Iterable[str | Path],
    output_root: str | Path,
) -> ExistingResultsTranslationPreparation:
    """Validate completed runs and prepare ordered sources without translating."""

    valid: list[ValidExistingResult] = []
    invalid: list[InvalidExistingResult] = []
    duplicates: list[DuplicateExistingResult] = []
    first_by_checkpoint: dict[str, ValidExistingResult] = {}

    for selected_value in selected_paths:
        selected_path = Path(selected_value)
        try:
            checkpoint_path = resolve_checkpoint_path(
                ProcessingMode.READING_ORDER,
                str(selected_path),
            )
            canonical = _canonical_key(checkpoint_path)
            if canonical in first_by_checkpoint:
                first = first_by_checkpoint[canonical]
                duplicates.append(DuplicateExistingResult(
                    selected_path,
                    first.selected_path,
                    first.resolved_checkpoint_path,
                ))
                continue

            resolved_checkpoint, presentation = reconstruct_presentation_from_reading_order(
                checkpoint_path
            )
            source_name = _source_run_directory(resolved_checkpoint).name
            ordering_index = len(valid)
            translation_source = TranslationApplicationSource(
                TranslationSourceItem(
                    source_item_id=f"existing-result-{ordering_index}",
                    display_name=source_name,
                    evidence_reference=f"reading-order:{resolved_checkpoint}",
                    ordering_index=ordering_index,
                    output_base_name=source_name,
                ),
                presentation,
            )
            item = ValidExistingResult(
                selected_path,
                resolved_checkpoint,
                source_name,
                presentation,
                translation_source,
            )
            valid.append(item)
            first_by_checkpoint[canonical] = item
        except (CheckpointValidationError, CheckpointLoadError, OSError) as error:
            invalid.append(InvalidExistingResult(
                selected_path,
                type(error).__name__,
                str(error),
            ))

    workspace = (
        _create_output_workspace(
            output_root,
            (_source_run_directory(item.resolved_checkpoint_path) for item in valid),
        )
        if valid else None
    )
    return ExistingResultsTranslationPreparation(
        tuple(valid),
        tuple(invalid),
        tuple(duplicates),
        tuple(item.translation_source for item in valid),
        workspace,
    )


def run_existing_results_translation(
    preparation: ExistingResultsTranslationPreparation,
    job_id: str,
    provider: TranslationProvider,
    target_languages: tuple[str, ...],
    grouping: TranslationOutputGrouping,
    formats: tuple[str, ...],
    *,
    source_language: str = "en",
    progress_callback: Callable[[int, int], None] | None = None,
) -> TranslationApplicationResult:
    """Translate all prepared sources once through the existing application stack."""

    if not isinstance(preparation, ExistingResultsTranslationPreparation):
        raise ValueError("preparation must be an ExistingResultsTranslationPreparation.")
    if not preparation.has_valid_sources or not preparation.translation_sources:
        raise ValueError("At least one valid existing result is required for translation.")
    if preparation.output_workspace is None or not preparation.output_workspace.is_dir():
        raise ValueError("Preparation requires an existing output workspace.")

    return run_translation_job(
        job_id,
        preparation.translation_sources,
        source_language,
        target_languages,
        provider,
        grouping,
        formats,
        preparation.output_workspace / "translations",
        progress_callback=progress_callback,
    )
