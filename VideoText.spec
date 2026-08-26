# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller configuration for the windowed VideoText desktop application."""

from pathlib import Path
import sys

from PyInstaller.utils.hooks import (
    collect_data_files,
    collect_dynamic_libs,
    collect_submodules,
    copy_metadata,
)


PROJECT_ROOT = Path(SPECPATH).resolve()
SOURCE_DIRECTORY = PROJECT_ROOT / "src"
PACKAGING_DIRECTORY = PROJECT_ROOT / "packaging"
ICON_FILE = PROJECT_ROOT / "icons" / "VT-icon.ico"
sys.path.insert(0, str(SOURCE_DIRECTORY))
sys.path.insert(0, str(PACKAGING_DIRECTORY))

from version_info import write_version_file


VERSION_FILE = PACKAGING_DIRECTORY / "VideoText_version.txt"
write_version_file(VERSION_FILE)

# Processing-service imports these modules lazily to keep GUI startup light.
RUNTIME_MODULES = [
    "app_info",
    "batch_processing",
    "batch_excel_exporter",
    "cache_manager",
    "config",
    "csv_exporter",
    "local_translation_provider",
    "excel_exporter",
    "export_manager",
    "frame_analyzer",
    "frame_saver",
    "help_content",
    "image_utils",
    "markdown_exporter",
    "models",
    "openai_translation_provider",
    "ocr_engine",
    "os_integration",
    "paragraph_reconstruction",
    "preferences",
    "processing_service",
    "reading_order",
    "run_workspace",
    "slide_consolidator",
    "structure_detection",
    "text_reconstruction",
    "video_reader",
    "video_source",
]

# PaddleOCR and Paddle load submodules and native libraries dynamically.
# PaddleX's public OCR import path, in contrast, imports and registers its
# pipeline and predictor implementations through normal package imports.
# PyInstaller therefore discovers those modules during Analysis; recursively
# collecting every PaddleX submodule would also analyze unrelated document,
# video, speech, and generative-AI implementations.
hiddenimports = list(RUNTIME_MODULES)
hiddenimports += collect_submodules("paddleocr")
hiddenimports += collect_submodules("paddle")
hiddenimports += ["ctranslate2", "sentencepiece"]
hiddenimports += collect_submodules("openai")

datas = collect_data_files("paddleocr", include_py_files=False)
datas += collect_data_files("paddlex", include_py_files=False)
datas += collect_data_files("paddle", include_py_files=False)
datas += [(str(ICON_FILE), "icons")]

binaries = collect_dynamic_libs("paddle")
binaries += collect_dynamic_libs("paddlex")
binaries += collect_dynamic_libs("cv2")
binaries += collect_dynamic_libs("ctranslate2")

# PaddleX validates OCR-core dependencies through importlib.metadata at runtime.
# PyInstaller collects the corresponding modules, but not their distribution
# metadata by default, which makes a frozen PaddleX OCR pipeline reject the
# otherwise bundled dependencies.
for distribution in (
    "imagesize",
    "opencv-contrib-python",
    "pyclipper",
    "pypdfium2",
    "python-bidi",
    "shapely",
    "ctranslate2",
    "sentencepiece",
    "openai",
    "httpx",
    "httpcore",
    "h11",
    "distro",
    "jiter",
    "certifi",
):
    datas += copy_metadata(distribution)


a = Analysis(
    [str(SOURCE_DIRECTORY / "gui.py")],
    pathex=[str(SOURCE_DIRECTORY)],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name="VideoText",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    icon=str(ICON_FILE),
    version=str(VERSION_FILE),
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    name="VideoText",
)
