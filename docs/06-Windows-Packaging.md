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

## Task 29D Replay and Offline Validation (2026-07-28)

The packaged executable successfully replayed only trusted checkpoints from
the Task 29C workspace. Each replay recreated Markdown, CSV, and the Excel
translation workbook in a distinct `_replay` workspace, and Markdown/CSV
matched the normal run byte-for-byte.

| Starting checkpoint | Replay workspace | Approximate elapsed time | Skipped stages | Executed stages |
| --- | --- | ---: | --- | --- |
| `candidate_frames.pkl` | `output\\task29d_candidate\\packaged_ocr_smoke_replay` | 32 seconds | Stable-frame analysis | OCR through export |
| `ocr_results.pkl` | `output\\task29d_ocr\\packaged_ocr_smoke_replay` | under 1 second | Stable-frame analysis and OCR | Reading order through export |
| `reading_order.pkl` | `output\\task29d_reading\\packaged_ocr_smoke_replay` | under 1 second | Stable-frame analysis, OCR, and reading order | Reconstruction, consolidation, presentation, and export |

The packaged full-video smoke test was also run while Wi-Fi was temporarily
disabled. Using the unchanged pre-existing cache at `C:\\Users\\sol\\.paddlex`,
PaddleOCR initialized and processed the video in 25 seconds. It created the
three pipeline checkpoints, three candidate-frame PNG files, Markdown, CSV,
and Excel in `output\\task29d_offline\\packaged_ocr_smoke`; Markdown and CSV
matched the prior normal run byte-for-byte. No download was possible during
this run and no model-download error appeared. Therefore, **offline operation
with pre-existing cached models succeeds**.

PaddleX 3.3.13 supports the `PADDLE_PDX_CACHE_HOME` environment variable.
A future clean-machine simulation can set it to a new empty temporary
directory before starting VideoText, leaving `C:\\Users\\sol\\.paddlex`
untouched. That simulation was intentionally not run here: with no models in
the override directory, first-run OCR is expected to require model download
and a clean offline machine remains unproven. Model weights are not bundled,
so that remains a release blocker. The missed final pending slide remains an
application frame-selection defect, not a packaging defect.

## Task 30B Terminal Stable-Slide Capture (2026-07-28)

The original diagnosis was refined using the deterministic smoke video. Its
three inter-slide difference scores (4.313, 5.295, and 5.237) are below the
normal transition threshold of 10.0, so the final slide was not an unresolved
pending transition. The first three candidates came from the five-second
static-frame fallback. Slide 4 begins at frame 54 and the 72-frame, 5 fps
video ends before another five seconds elapse.

Frame selection now confirms a terminal stability window using the existing
quiet-frame threshold and the existing five-frame stability requirement. It
captures a visible terminal frame only when that window is cumulatively stable
and it differs from the most recently saved candidate. The same save helper is
used for normal transitions, static fallback, and EOF; later captures reject
black frames and exact duplicate images. This preserves the normal transition
threshold and avoids blanket last-frame capture.

Source validation against `sample_videos/packaged_ocr_smoke.avi` now produces
four candidate frames at 0, 25, 50, and 71 (0.0, 5.0, 10.0, and 14.2 seconds).
The first three candidate PNGs are byte-for-byte identical to the prior
packaged run. With the PaddleX model-source check disabled for this local
validation (`PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK=True`), the source run
completed OCR, reading order, consolidation, and all three exports. It
produced four slides; Slide 4 is the expected `3. Export Markdown CSV Excel`
content, and the progressive Slide 3 paragraph remains unchanged. Replay from
the new `reading_order.pkl` produced four slides plus Markdown, CSV, and Excel;
its Markdown is byte-for-byte identical to the normal source run.

## Task 30C Packaged Terminal-Slide Validation (2026-07-28)

A fresh PyInstaller build completed normally with Python 3.12.10 from the
project virtual environment. The build took approximately 4 minutes 48 seconds
and created `dist\VideoText\VideoText.exe` (about 231 MiB) with a distribution
folder of about 819 MiB. The only collection warnings were the pre-existing
optional PaddleX serving-plugin and Paddle TensorRT warnings.

The rebuilt executable processed `packaged_ocr_smoke.avi` in 36 seconds. Its
normal run created four candidate PNGs at frames 0, 25, 50, and 71, all three
checkpoints, Markdown, CSV, and Excel. The consolidated presentation has four
slides. Slide 4 (`3. Export Markdown CSV Excel`) is present in every export;
Slides 1--3 and the progressive Slide 3 paragraph remain unchanged. The GUI
showed its completion summary and remained responsive during the run.

Advanced Mode replay from that packaged run's `reading_order.pkl` loaded four
frames, skipped frame analysis, OCR, and reading order, and created a distinct
`packaged_ocr_smoke_replay_2` workspace containing Markdown, CSV, and Excel.
Its Markdown and CSV are byte-for-byte identical to the packaged normal run,
and its Excel workbook includes Slide 4. The terminal stable-slide defect is
therefore resolved in both packaged full-video and replay processing.
