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
