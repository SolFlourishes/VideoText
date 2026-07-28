"""Focused tests for VideoText's in-app Help and About system."""

import sys
from pathlib import Path
import unittest


sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import gui
from app_info import APP_COPYRIGHT, APP_NAME, APP_RELEASE, APP_STATUS
from help_content import get_about_sections, get_about_text, get_how_to_use_text


class HelpAboutTests(unittest.TestCase):
    class _FakeText:
        """Record Text-widget calls without requiring a display server."""

        def __init__(self):
            self.tags: set[str] = set()
            self.insertions: list[tuple[str, str]] = []

        def tag_configure(self, tag: str, **_options) -> None:
            self.tags.add(tag)

        def insert(self, _index: str, text: str, tag: str) -> None:
            self.insertions.append((text, tag))

    def test_how_to_use_covers_normal_advanced_exports_and_troubleshooting(self):
        content = get_how_to_use_text()

        for required_text in (
            "VideoText User Guide",
            "What is VideoText?",
            "Getting Started",
            "Processing Stages",
            "Batch Processing",
            "Advanced Mode (Replay)",
            "Output Folder Structure",
            "Tips",
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

    def test_shared_application_metadata_is_available_for_about_and_packaging(self):
        self.assertEqual(APP_NAME, "VideoText")
        self.assertEqual(APP_RELEASE, "0.9.0")
        self.assertEqual(APP_STATUS, "Feature-Complete Development Build")
        self.assertEqual(APP_COPYRIGHT, "© 2026 Sol Roberts-Lieb")

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

    def test_user_guide_uses_reusable_text_tags(self):
        source = Path(gui.__file__).read_text(encoding="utf-8")

        self.assertIn("def _insert_formatted_user_guide", source)
        for tag in ("title", "heading", "subheading", "body", "bullet", "code", "note"):
            with self.subTest(tag=tag):
                self.assertIn(f'"{tag}"', source)
        self.assertIn("formatted_guide=True", source)

    def test_guide_rendering_keeps_text_selectable_and_dialog_actions_unchanged(self):
        source = Path(gui.__file__).read_text(encoding="utf-8")

        self.assertIn("_insert_formatted_user_guide(help_text, content)", source)
        self.assertIn('help_text.configure(state="disabled")', source)
        self.assertIn('dialog.bind("<Escape>"', source)
        self.assertIn('text="Close"', source)

    def test_user_guide_is_independent_of_the_current_release(self):
        self.assertNotIn(APP_RELEASE, get_how_to_use_text())

    def test_user_guide_warns_that_replay_caches_must_be_trusted(self):
        content = get_how_to_use_text().lower()

        self.assertIn("replay cache files created by videotext", content)
        self.assertIn("trusted computer", content)
        self.assertIn("pickle", content)

    def test_about_uses_shared_metadata_and_semantic_formatting_tags(self):
        source = Path(gui.__file__).read_text(encoding="utf-8")

        self.assertIn("f\"Version {APP_RELEASE}\"", source)
        for section in (
            "What VideoText Does",
            "Privacy and Storage",
            "Application Information",
        ):
            self.assertIn(section, get_about_text())
        for tag in (
            "about_title",
            "about_version",
            "about_status",
            "about_heading",
            "about_body",
            "about_footer",
        ):
            with self.subTest(tag=tag):
                self.assertIn(f'"{tag}"', source)

    def test_about_inserts_title_version_status_and_footer_with_tags(self):
        source = Path(gui.__file__).read_text(encoding="utf-8")

        self.assertIn('APP_NAME + "\\n", "about_title"', source)
        self.assertIn('version_text + "\\n", "about_version"', source)
        self.assertIn('APP_STATUS + "\\n", "about_status"', source)
        self.assertIn('APP_COPYRIGHT + "\\n", "about_footer"', source)

    def test_about_renderer_uses_shared_metadata_with_its_intended_tags(self):
        text = self._FakeText()

        gui._insert_formatted_about(text, get_about_sections())

        self.assertIn((APP_NAME + "\n", "about_title"), text.insertions)
        self.assertIn(
            (f"Version {APP_RELEASE}\n", "about_version"),
            text.insertions,
        )
        self.assertIn((APP_STATUS + "\n", "about_status"), text.insertions)
        self.assertIn(
            ("\n" + APP_COPYRIGHT + "\n", "about_footer"),
            text.insertions,
        )
        self.assertTrue({
            "about_title",
            "about_version",
            "about_status",
            "about_heading",
            "about_body",
            "about_footer",
        }.issubset(text.tags))


if __name__ == "__main__":
    unittest.main()
