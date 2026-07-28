"""Generate Windows executable version metadata from VideoText app_info."""

from pathlib import Path
import sys


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SOURCE_DIRECTORY = PROJECT_ROOT / "src"
if str(SOURCE_DIRECTORY) not in sys.path:
    sys.path.insert(0, str(SOURCE_DIRECTORY))

from app_info import APP_COPYRIGHT, APP_NAME, APP_RELEASE, APP_STATUS


def windows_version_tuple(release: str = APP_RELEASE) -> tuple[int, int, int, int]:
    """Convert a dotted release string into PyInstaller's four-part version."""

    parts = release.split(".")
    if not 1 <= len(parts) <= 4 or any(not part.isdigit() for part in parts):
        raise ValueError(f"Invalid release version: {release}")

    values = [int(part) for part in parts]
    return tuple((values + [0, 0, 0, 0])[:4])


def render_version_info() -> str:
    """Return the PyInstaller version-resource source for the current release."""

    version = windows_version_tuple()
    return f"""# UTF-8
VSVersionInfo(
  ffi=FixedFileInfo(
    filevers={version},
    prodvers={version},
    mask=0x3f,
    flags=0x0,
    OS=0x40004,
    fileType=0x1,
    subtype=0x0,
    date=(0, 0)
  ),
  kids=[
    StringFileInfo([
      StringTable(
        '040904B0',
        [
          StringStruct('CompanyName', 'Sol Roberts-Lieb'),
          StringStruct('FileDescription', '{APP_NAME}'),
          StringStruct('FileVersion', '{APP_RELEASE}'),
          StringStruct('InternalName', '{APP_NAME}'),
          StringStruct('LegalCopyright', '{APP_COPYRIGHT}'),
          StringStruct('OriginalFilename', '{APP_NAME}.exe'),
          StringStruct('ProductName', '{APP_NAME}'),
          StringStruct('ProductVersion', '{APP_RELEASE}'),
          StringStruct('Comments', '{APP_STATUS}')
        ]
      )
    ]),
    VarFileInfo([VarStruct('Translation', [1033, 1200])])
  ]
)
"""


def write_version_file(output_path: Path) -> Path:
    """Write generated version metadata beneath the packaging directory."""

    output_path.write_text(render_version_info(), encoding="utf-8")
    return output_path
