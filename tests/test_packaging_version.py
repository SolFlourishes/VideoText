"""Focused tests for generated Windows executable version metadata."""

import importlib.util
from pathlib import Path
import sys
import tempfile
import unittest


PROJECT_ROOT = Path(__file__).resolve().parent.parent
VERSION_HELPER_PATH = PROJECT_ROOT / "packaging" / "version_info.py"


def load_version_helper():
    spec = importlib.util.spec_from_file_location(
        "videotext_packaging_version_info",
        VERSION_HELPER_PATH,
    )
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


version_info = load_version_helper()


class PackagingVersionTests(unittest.TestCase):
    def test_release_becomes_a_four_part_windows_version(self):
        self.assertEqual(version_info.windows_version_tuple(), (0, 9, 0, 0))

    def test_generated_resource_uses_shared_app_metadata(self):
        content = version_info.render_version_info()

        self.assertIn(version_info.APP_RELEASE, content)
        self.assertIn(version_info.APP_NAME, content)
        self.assertIn(version_info.APP_STATUS, content)
        self.assertIn(version_info.APP_COPYRIGHT, content)

    def test_write_version_file_writes_generated_content(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            output_path = Path(temporary_directory) / "VideoText_version.txt"
            version_info.write_version_file(output_path)

            self.assertEqual(output_path.read_text(encoding="utf-8"), version_info.render_version_info())


if __name__ == "__main__":
    unittest.main()
