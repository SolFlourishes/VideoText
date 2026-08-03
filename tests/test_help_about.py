"""Focused tests for VideoText's in-app Help and About system."""

import sys
from pathlib import Path
import unittest


sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import gui
from app_info import APP_COPYRIGHT, APP_NAME, APP_RELEASE, APP_STATUS
from help_content import (
    get_about_sections,
    get_about_text,
    get_accuracy_validation_text,
    get_how_to_use_text,
)


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
            "OCR Quality",
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
        self.assertIn("ocr quality", content)
        self.assertIn("not automatically rewritten", content)

    def test_user_guide_explains_version_13_ocr_quality_and_csv_fields(self):
        content = get_how_to_use_text().lower()

        for field in (
            "ocr_region_count",
            "ocr_confidence_minimum",
            "ocr_confidence_maximum",
            "ocr_confidence_mean",
            "ocr_confidence_median",
            "ocr_below_threshold_count",
            "ocr_below_threshold_proportion",
            "ocr_confidence_threshold",
        ):
            with self.subTest(field=field):
                self.assertIn(field, content)
        self.assertIn("active 60%", content)
        self.assertIn("descriptive only", content)
        self.assertIn("do not rewrite or correct", content)
        self.assertIn("low-confidence regions", content)

    def test_accuracy_validation_topic_covers_expected_sections(self):
        content = get_accuracy_validation_text()

        for section in (
            "Accuracy & Validation",
            "What VideoText Is Designed For",
            "How VideoText Works",
            "Expected Accuracy",
            "Factors That Affect Accuracy",
            "Validation",
            "Engineering Philosophy",
            "Future Validation",
            "Practical Recommendation",
        ):
            with self.subTest(section=section):
                self.assertIn(section, content)

        self.assertIn("automated regression testing", content)
        self.assertIn("AI-assisted comparison", content)
        self.assertIn("original video", content)

    def test_shared_application_metadata_is_available_for_about_and_packaging(self):
        self.assertEqual(APP_NAME, "VideoText")
        self.assertEqual(APP_RELEASE, "1.3.0")
        self.assertEqual(APP_STATUS, "Release")
        self.assertEqual(APP_COPYRIGHT, "© 2026 Sol Roberts-Lieb")

    def test_gui_has_help_menu_with_separate_how_to_and_about_commands(self):
        source = Path(gui.__file__).read_text(encoding="utf-8")

        self.assertIn('menu_bar.add_cascade(label="Help"', source)
        self.assertIn('label="How to Use VideoText"', source)
        self.assertIn('label="Accuracy & Validation"', source)
        self.assertIn('label="About VideoText"', source)
        self.assertLess(
            source.index('label="Accuracy & Validation"'),
            source.index('label="About VideoText"'),
        )

    def test_accuracy_topic_uses_the_existing_formatted_help_dialog(self):
        source = Path(gui.__file__).read_text(encoding="utf-8")

        self.assertIn("def _show_accuracy_validation", source)
        self.assertIn("get_accuracy_validation_text()", source)
        self.assertIn("formatted_accuracy=True", source)
        self.assertIn("_insert_formatted_accuracy_validation(help_text, content)", source)

    def test_accuracy_topic_uses_shared_title_and_heading_tags(self):
        text = self._FakeText()

        gui._insert_formatted_accuracy_validation(
            text,
            get_accuracy_validation_text(),
        )

        self.assertIn(("Accuracy & Validation\n", "title"), text.insertions)
        self.assertIn(("Validation\n", "heading"), text.insertions)
        self.assertTrue({"title", "heading", "body"}.issubset(text.tags))

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

    def test_user_guide_explains_direct_video_url_limits(self):
        content = get_how_to_use_text().lower()

        self.assertIn("direct http or https links", content)
        self.assertIn("youtube watch pages", content)
        self.assertIn("protected cloud-sharing pages", content)
        self.assertIn("authorized to access", content)

    def test_about_uses_shared_metadata_and_semantic_formatting_tags(self):
        source = Path(gui.__file__).read_text(encoding="utf-8")

        self.assertIn("f\"Version {APP_RELEASE}\"", source)
        for section in (
            "What VideoText Does",
            "Privacy and Storage",
            "Application Information",
            "OCR Quality",
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

    def test_accessible_menu_mnemonics_and_dialog_keyboard_bindings_exist(self):
        source = Path(gui.__file__).read_text(encoding="utf-8")

        self.assertIn('label="File", underline=0', source)
        self.assertIn('label="Edit", underline=0', source)
        self.assertIn('label="Help", underline=0', source)
        self.assertGreaterEqual(source.count('dialog.bind("<Return>"'), 4)

    def test_dialog_close_restores_focus_to_the_primary_action(self):
        class FocusTarget:
            def __init__(self):
                self.focused = False

            def focus_set(self):
                self.focused = True

        app = object.__new__(gui.VideoTextApp)
        app.process_button = FocusTarget()

        gui.VideoTextApp._restore_main_focus(app)

        self.assertTrue(app.process_button.focused)

    def test_dialog_sizing_stays_within_the_available_screen_area(self):
        class Dialog:
            def __init__(self):
                self.geometry_value = ""

            def winfo_screenwidth(self):
                return 800

            def winfo_screenheight(self):
                return 600

            def geometry(self, value):
                self.geometry_value = value

        class Parent:
            def update_idletasks(self):
                pass

            def winfo_rootx(self):
                return 100

            def winfo_rooty(self):
                return 80

            def winfo_width(self):
                return 400

            def winfo_height(self):
                return 300

        dialog = Dialog()
        gui._center_dialog(dialog, Parent(), preferred_width=1200, preferred_height=900)

        self.assertEqual(dialog.geometry_value, "720x480+0+0")


if __name__ == "__main__":
    unittest.main()
