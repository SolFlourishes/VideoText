# Windows Packaging Diagnostic Build

This is a developer diagnostic build, not an end-user installer. Build on
Windows with the same Python environment used for VideoText development.

Install runtime dependencies and the separate build dependency:

    python -m pip install -r requirements.txt
    python -m pip install -r requirements-packaging.txt

Build the windowed GUI executable from the repository root:

    ./build_windows.ps1 -Clean

The expected result is dist/VideoText/VideoText.exe. Launch that executable
manually and collect build/VideoText/warn-VideoText.txt if PyInstaller reports
missing modules or DLLs.

The initial build collects PaddleOCR/Paddle package resources and native
libraries, but does not bundle OCR model weights. PaddleOCR 3.x may download
models on first OCR use unless complete local model paths or a user-level model
cache are available. Offline OCR is therefore a remaining beta blocker.

Do not package tests, documentation, sample videos, output workspaces, caches,
or developer tools.

## Task 29B Diagnostic Validation (2026-07-28)

The first diagnostic build succeeded from the project virtual environment with:

    .\build_windows.ps1 -Clean

The executable was created at `dist\VideoText\VideoText.exe`. The build took
approximately 7 minutes 19 seconds and produced a 230 MiB executable plus a
819 MiB `dist\VideoText` folder containing 4,378 files. The executable starts
the VideoText window without a console window and exits normally.

`build\VideoText\warn-VideoText.txt` contains mostly optional or
platform-specific import-analysis warnings. It also records optional PaddleX
serving and Paddle TensorRT collection warnings; neither prevented the GUI
from launching. The diagnostic build currently includes some unexpectedly
large transitive packages from the development environment, including Qt /
PySide files. They were retained for this first validation and require a
separate packaging-scope review rather than removal during this diagnostic
task.

No representative video was available outside development and generated
directories, so an end-to-end OCR/export smoke test was not run. The observed
user-level PaddleX model cache was `C:\\Users\\sol\\.paddlex` (101 files,
about 268 MiB). OCR model weights were not bundled into `dist`; offline OCR is
therefore still unproven and remains a release blocker until a processing
smoke test demonstrates the required model behavior.

## Task 29C Packaged OCR Validation (2026-07-28)

The deterministic ignored smoke video `sample_videos/packaged_ocr_smoke.avi`
was used for the first frozen processing test. It contains four static slides:
the title, a numbered two-line item, a numbered three-line progressive item,
and an export label.

The initial frozen OCR attempt created candidate frames but failed during
PaddleOCR pipeline creation. PaddleX checks its OCR-core dependencies through
`importlib.metadata`; PyInstaller had bundled their modules but not their
distribution metadata. The packaging spec now includes metadata for imagesize,
opencv-contrib-python, pyclipper, pypdfium2, python-bidi, and shapely.

After rebuilding, the packaged normal run succeeded in the isolated
`packaged_ocr_smoke` workspace. It created three readable candidate PNGs,
`candidate_frames.pkl`, `ocr_results.pkl`, `reading_order.pkl`, Markdown,
CSV, and the Excel translation workbook. It completed in 38 seconds using the
pre-existing user cache at `C:\\Users\\sol\\.paddlex`; no model download was
observed. The cache contains the document-orientation, unwarping,
textline-orientation, text-detection, and English-recognition models used by
PaddleOCR.

OCR correctly extracted the title and the two progressive paragraphs. The
final fourth slide was absent because the current stable-frame selector does
not save a pending transition at end-of-video. Markdown and CSV flatten the
continuation lines into one paragraph text, while the Excel workbook preserves
them as visually separated continuation lines. These are existing pipeline
behaviors, not frozen-build-specific changes.

Offline operation on a clean machine remains unproven because model weights
are not bundled. A cache-backed offline confirmation and the replay checks
remain required before release readiness can be claimed.
