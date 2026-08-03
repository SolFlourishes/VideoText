"""Focused checks for the packaged and Tkinter VideoText icon."""

from pathlib import Path
import sys
import unittest


PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

import gui


class BrandingTests(unittest.TestCase):
    def test_source_icon_exists_and_gui_resolves_it(self):
        icon_path = PROJECT_ROOT / "icons" / "VT-icon.ico"

        self.assertTrue(icon_path.is_file())
        self.assertEqual(gui._application_icon_path(), icon_path)

    def test_packaging_embeds_and_bundles_the_application_icon(self):
        specification = (PROJECT_ROOT / "VideoText.spec").read_text(encoding="utf-8")

        self.assertIn('ICON_FILE = PROJECT_ROOT / "icons" / "VT-icon.ico"', specification)
        self.assertIn('datas += [(str(ICON_FILE), "icons")]', specification)
        self.assertIn('icon=str(ICON_FILE)', specification)


if __name__ == "__main__":
    unittest.main()
