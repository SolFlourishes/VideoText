"""Focused contracts for isolated PyInstaller build identities."""

import importlib.util
import os
from pathlib import Path
import sys
import unittest


PROJECT_ROOT = Path(__file__).resolve().parent.parent
VERSION_HELPER_PATH = PROJECT_ROOT / "packaging" / "version_info.py"


def load_version_helper():
    spec = importlib.util.spec_from_file_location(
        "videotext_build_identity_version_info",
        VERSION_HELPER_PATH,
    )
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


version_info = load_version_helper()


class PackagingBuildIdentityTests(unittest.TestCase):
    def test_default_identity_preserves_release_convention(self):
        self.assertEqual("VideoText", version_info.DEFAULT_BUILD_NAME)
        specification = (PROJECT_ROOT / "VideoText.spec").read_text(encoding="utf-8")
        self.assertIn("os.environ.get(BUILD_NAME_ENVIRONMENT_VARIABLE, DEFAULT_BUILD_NAME)", specification)
        self.assertIn("name=BUILD_NAME", specification)

    def test_development_identity_is_valid_and_distinct(self):
        name = version_info.validate_build_name("VideoText-1.8-dev")
        self.assertEqual(PROJECT_ROOT / "build" / name, PROJECT_ROOT / "build" / name)
        self.assertNotEqual(PROJECT_ROOT / "build" / "VideoText", PROJECT_ROOT / "build" / name)
        self.assertNotEqual(PROJECT_ROOT / "dist" / "VideoText", PROJECT_ROOT / "dist" / name)

    def test_unsafe_names_are_rejected_instead_of_sanitized(self):
        for value in (
            "", ".", "..", "../VideoText", r"VideoText\dev", "VideoText/dev",
            "VideoText dev", "C:VideoText", "VideoText.", "CON", "LPT1.exe",
        ):
            with self.subTest(value=value), self.assertRaises(ValueError):
                version_info.validate_build_name(value)

    def test_version_resource_path_is_build_specific(self):
        specification = (PROJECT_ROOT / "VideoText.spec").read_text(encoding="utf-8")
        self.assertIn('PROJECT_ROOT / "build" / BUILD_NAME / f"{BUILD_NAME}_version.txt"', specification)
        self.assertNotIn('PACKAGING_DIRECTORY / "VideoText_version.txt"', specification)

    def test_script_derives_clean_and_output_targets_from_build_name(self):
        script = (PROJECT_ROOT / "build_windows.ps1").read_text(encoding="utf-8")
        self.assertIn('[string]$BuildName = "VideoText"', script)
        self.assertIn('$buildDirectory', script)
        self.assertIn('$distributionDirectory', script)
        self.assertIn('$topLevelExecutable', script)
        self.assertIn('$collectedExecutable', script)
        self.assertIn('--workpath $buildDirectory', script)
        clean_section = script[script.index("if ($Clean)"):script.index("$env:PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK")]
        self.assertNotIn('"build/VideoText"', clean_section)
        self.assertNotIn('"dist/VideoText"', clean_section)

    def test_script_passes_one_identity_to_spec_and_restores_environment(self):
        script = (PROJECT_ROOT / "build_windows.ps1").read_text(encoding="utf-8")
        self.assertIn('$env:VIDEOTEXT_BUILD_NAME = $BuildName', script)
        self.assertIn('$env:VIDEOTEXT_BUILD_NAME = $previousBuildName', script)
        self.assertEqual(
            "VIDEOTEXT_BUILD_NAME",
            version_info.BUILD_NAME_ENVIRONMENT_VARIABLE,
        )

    def test_script_supports_an_authoritative_release_python(self):
        script = (PROJECT_ROOT / "build_windows.ps1").read_text(encoding="utf-8")
        self.assertIn('[string]$PythonExecutable = ""', script)
        self.assertIn("$PythonExecutable", script)

    def test_existing_production_path_does_not_change_development_targets(self):
        production = PROJECT_ROOT / "dist" / "VideoText"
        development = PROJECT_ROOT / "dist" / version_info.validate_build_name("VideoText-1.8-dev")
        self.assertNotEqual(os.path.normcase(production), os.path.normcase(development))
        self.assertEqual(development / "VideoText-1.8-dev.exe", development / "VideoText-1.8-dev.exe")


if __name__ == "__main__":
    unittest.main()
