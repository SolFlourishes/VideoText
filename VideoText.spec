# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller configuration for the windowed VideoText desktop application."""

from pathlib import Path
import sys

from PyInstaller.utils.hooks import (
    collect_data_files,
    collect_dynamic_libs,
    collect_submodules,
)


PROJECT_ROOT = Path(SPECPATH).resolve()
SOURCE_DIRECTORY = PROJECT_ROOT / "src"
PACKAGING_DIRECTORY = PROJECT_ROOT / "packaging"
sys.path.insert(0, str(SOURCE_DIRECTORY))
sys.path.insert(0, str(PACKAGING_DIRECTORY))

from version_info import write_version_file


VERSION_FILE = PACKAGING_DIRECTORY / "VideoText_version.txt"
write_version_file(VERSION_FILE)

# Processing-service imports these modules lazily to keep GUI startup light.
RUNTIME_MODULES = [
    "app_info",
    "batch_processing",
    "cache_manager",
    "config",
    "csv_exporter",
    "excel_exporter",
    "export_manager",
    "frame_analyzer",
    "frame_saver",
    "help_content",
    "image_utils",
    "markdown_exporter",
    "models",
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
]

# PaddleOCR 3.x, PaddleX, and Paddle load submodules and native libraries
# dynamically. These collections remain limited to VideoText's OCR runtime
# dependencies.
hiddenimports = list(RUNTIME_MODULES)
hiddenimports += collect_submodules("paddleocr")
hiddenimports += collect_submodules("paddlex")
hiddenimports += collect_submodules("paddle")

datas = collect_data_files("paddleocr", include_py_files=False)
datas += collect_data_files("paddlex", include_py_files=False)
datas += collect_data_files("paddle", include_py_files=False)

binaries = collect_dynamic_libs("paddle")
binaries += collect_dynamic_libs("paddlex")
binaries += collect_dynamic_libs("cv2")


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
