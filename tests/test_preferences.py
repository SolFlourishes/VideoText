"""Focused tests for persistent VideoText user preferences."""

import json
import os
import sys
import tempfile
from pathlib import Path
import unittest
from unittest.mock import patch


sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import gui
from os_integration import open_folder
from preferences import (
    Preferences,
    load_preferences,
    preferences_path,
    remember_folder,
    save_preferences,
    valid_initial_directory,
)


class PreferencesTests(unittest.TestCase):
    def setUp(self):
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary_directory.cleanup)
        self.root = Path(self.temporary_directory.name)
        self.preferences_file = self.root / "application_data" / "preferences.json"

    def test_missing_file_loads_defaults(self):
        preferences = load_preferences(self.preferences_file)

        self.assertEqual(preferences.default_output_folder, "")
        self.assertEqual(preferences.default_export_formats, ["markdown", "csv", "excel"])
        self.assertTrue(preferences.remember_last_folders)
        self.assertFalse(preferences.open_output_folder_after_completion)

    def test_preferences_save_and_reload(self):
        output_folder = self.root / "output"
        output_folder.mkdir()
        saved = Preferences(
            default_output_folder=str(output_folder),
            default_export_formats=["csv"],
            remember_last_folders=False,
            open_output_folder_after_completion=True,
        )

        save_preferences(saved, self.preferences_file)
        loaded = load_preferences(self.preferences_file)

        self.assertEqual(loaded.default_output_folder, str(output_folder))
        self.assertEqual(loaded.default_export_formats, ["csv"])
        self.assertFalse(loaded.remember_last_folders)
        self.assertTrue(loaded.open_output_folder_after_completion)

    def test_missing_and_invalid_values_fall_back_safely(self):
        self.preferences_file.parent.mkdir(parents=True)
        self.preferences_file.write_text(json.dumps({
            "default_export_formats": ["excel", "unknown"],
            "remember_last_folders": "yes",
            "open_output_folder_after_completion": "no",
            "last_output_folder": 42,
        }), encoding="utf-8")

        loaded = load_preferences(self.preferences_file)

        self.assertEqual(loaded.default_export_formats, ["excel"])
        self.assertTrue(loaded.remember_last_folders)
        self.assertFalse(loaded.open_output_folder_after_completion)
        self.assertEqual(loaded.last_output_folder, "")

    def test_malformed_json_does_not_crash_loading(self):
        self.preferences_file.parent.mkdir(parents=True)
        self.preferences_file.write_text("{not valid json", encoding="utf-8")

        self.assertEqual(load_preferences(self.preferences_file), Preferences())

    def test_appdata_storage_path_is_outside_project_and_output(self):
        app_data = self.root / "AppData" / "Roaming"
        with patch.dict(os.environ, {"APPDATA": str(app_data)}, clear=False):
            path = preferences_path()

        self.assertEqual(path, app_data / "VideoText" / "preferences.json")
        self.assertNotEqual(path.parent, Path.cwd())

    def test_remembered_folders_respect_the_enabled_setting(self):
        folder = self.root / "videos"
        folder.mkdir()
        preferences = Preferences()
        with patch("preferences.save_preferences"):
            remember_folder(preferences, "last_single_video_folder", folder)
        self.assertEqual(preferences.last_single_video_folder, str(folder))

        preferences.remember_last_folders = False
        with patch("preferences.save_preferences"):
            remember_folder(preferences, "last_single_video_folder", self.root)
        self.assertEqual(preferences.last_single_video_folder, str(folder))
        self.assertIsNone(valid_initial_directory(str(self.root / "missing")))

    def test_gui_preferences_validation_and_startup_defaults_are_present(self):
        source = Path(gui.__file__).read_text(encoding="utf-8")

        self.assertIn('label="Preferences..."', source)
        self.assertIn("Select at least one default export format.", source)
        self.assertIn("Default output folder must be an existing directory.", source)
        self.assertIn("self.preferences.default_export_formats", source)
        self.assertIn("Restore Defaults", source)

    def test_open_folder_after_success_is_nonfatal_and_failures_do_not_open(self):
        app = object.__new__(gui.VideoTextApp)
        app.preferences = Preferences(open_output_folder_after_completion=True)
        messages = []
        app._append_log = messages.append

        with patch.object(gui, "open_folder", return_value="Explorer unavailable") as opener:
            gui.VideoTextApp._open_completed_folder(app, self.root)

        opener.assert_called_once_with(self.root)
        self.assertIn("Warning: Explorer unavailable", messages)

        app.preferences.open_output_folder_after_completion = False
        with patch.object(gui, "open_folder") as opener:
            gui.VideoTextApp._open_completed_folder(app, self.root)
        opener.assert_not_called()

    def test_os_folder_open_failure_returns_warning(self):
        folder = self.root / "output"
        folder.mkdir()
        with patch("os_integration.sys.platform", "win32"), patch.object(
            os,
            "startfile",
            side_effect=OSError("blocked"),
            create=True,
        ):
            warning = open_folder(folder)

        self.assertIn("Could not open output folder", warning)


if __name__ == "__main__":
    unittest.main()
