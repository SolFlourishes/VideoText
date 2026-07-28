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
