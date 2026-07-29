"""Focused safeguards for the intentionally narrow PaddleX build scope."""

from pathlib import Path
import unittest


PROJECT_ROOT = Path(__file__).resolve().parent.parent
SPEC_PATH = PROJECT_ROOT / "VideoText.spec"


class PackagingScopeTests(unittest.TestCase):
    def test_spec_does_not_recursively_collect_every_paddlex_module(self):
        spec_text = SPEC_PATH.read_text(encoding="utf-8")

        self.assertNotIn('collect_submodules("paddlex")', spec_text)

    def test_spec_retains_required_paddlex_resources(self):
        spec_text = SPEC_PATH.read_text(encoding="utf-8")

        self.assertIn('collect_data_files("paddlex", include_py_files=False)', spec_text)
        self.assertIn('collect_dynamic_libs("paddlex")', spec_text)


if __name__ == "__main__":
    unittest.main()
