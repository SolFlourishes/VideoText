"""Focused tests for VideoText's in-app Help and About system."""

import sys
from pathlib import Path
import unittest


sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import gui
from help_content import get_about_text, get_how_to_use_text


class HelpAboutTests(unittest.TestCase):
    def test_how_to_use_covers_normal_advanced_exports_and_troubleshooting(self):
        content = get_how_to_use_text()

        for required_text in (
            "Normal Mode",
            "Advanced Mode",
            "Candidate frames cache",
            "OCR results cache",
            "Reading-order cache",
            "checkpoint",
            "Markdown",
            "CSV",
            "Excel",
            "Troubleshooting",
        ):
            with self.subTest(required_text=required_text):
                self.assertIn(required_text, content)

    def test_about_explains_local_storage_and_no_administrator_requirements(self):
        content = get_about_text().lower()

        self.assertIn("locally", content)
        self.assertIn("output folder", content)
        self.assertIn("administrator rights", content)
        self.assertIn("registry", content)
        self.assertIn("background services", content)

    def test_gui_has_help_menu_with_separate_how_to_and_about_commands(self):
        source = Path(gui.__file__).read_text(encoding="utf-8")

        self.assertIn('menu_bar.add_cascade(label="Help"', source)
        self.assertIn('label="How to Use VideoText"', source)
        self.assertIn('label="About VideoText"', source)

    def test_help_dialog_is_custom_scrollable_read_only_and_escape_closable(self):
        source = Path(gui.__file__).read_text(encoding="utf-8")

        self.assertIn("def _show_help_dialog", source)
        self.assertIn("tk.Toplevel(self.master)", source)
        self.assertIn("scrolledtext.ScrolledText", source)
        self.assertIn('help_text.configure(state="disabled")', source)
        self.assertIn('dialog.bind("<Escape>"', source)
        self.assertIn("dialog.resizable(True, True)", source)


if __name__ == "__main__":
    unittest.main()
