"""Command-line selection for single, resumed, and batch VideoText processing."""

from enum import Enum

from processing_service import ProcessingMode


class CliProcessingMode(Enum):
    """Additional command-line choices that do not map to one checkpoint mode."""

    BATCH_FILES = "batch_files"
    BATCH_FOLDER = "batch_folder"


def select_processing_mode() -> ProcessingMode:
    """Ask the user where the shared processing service should start."""

    print()
    print("=" * 40)
    print("VideoText. Where would you like to begin?")
    print("=" * 40)
    print("1. Full video")
    print("2. Resume from candidate frames")
    print("3. Resume from OCR results")
    print("4. Resume from reading order")
    print()

    choice = input("Select stage [1]: ").strip()

    if choice == "" or choice == "1":
        return ProcessingMode.FULL_VIDEO

    if choice == "2":
        return ProcessingMode.CANDIDATE_FRAMES

    if choice == "3":
        return ProcessingMode.OCR_RESULTS

    if choice == "4":
        return ProcessingMode.READING_ORDER

    print("Invalid selection. Starting full video processing.")

    return ProcessingMode.FULL_VIDEO


def select_cli_mode() -> ProcessingMode | CliProcessingMode:
    """Prompt for all supported CLI processing entry points."""

    print()
    print("=" * 40)
    print("VideoText. Where would you like to begin?")
    print("=" * 40)
    print("1. Full video")
    print("2. Batch: multiple files")
    print("3. Batch: folder")
    print("4. Resume from candidate frames")
    print("5. Resume from OCR results")
    print("6. Resume from reading order")
    print()

    choice = input("Select mode [1]: ").strip()
    choices = {
        "": ProcessingMode.FULL_VIDEO,
        "1": ProcessingMode.FULL_VIDEO,
        "2": CliProcessingMode.BATCH_FILES,
        "3": CliProcessingMode.BATCH_FOLDER,
        "4": ProcessingMode.CANDIDATE_FRAMES,
        "5": ProcessingMode.OCR_RESULTS,
        "6": ProcessingMode.READING_ORDER,
    }

    if choice in choices:
        return choices[choice]

    print("Invalid selection. Starting full video processing.")
    return ProcessingMode.FULL_VIDEO
