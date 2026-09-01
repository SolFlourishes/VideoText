"""Focused safeguards for the intentionally narrow PaddleX build scope."""

from pathlib import Path
import unittest


PROJECT_ROOT = Path(__file__).resolve().parent.parent
SPEC_PATH = PROJECT_ROOT / "VideoText.spec"


class PackagingScopeTests(unittest.TestCase):
    def test_portable_spec_uses_true_one_folder_structure(self):
        spec_text = SPEC_PATH.read_text(encoding="utf-8")

        exe_section = spec_text[spec_text.index("exe = EXE("):spec_text.index("coll = COLLECT(")]
        self.assertIn("exclude_binaries=True", exe_section)
        self.assertNotIn("a.binaries", exe_section)
        self.assertNotIn("a.datas", exe_section)
        self.assertIn("a.binaries", spec_text[spec_text.index("coll = COLLECT("):])

    def test_evaluation_and_development_packages_are_excluded(self):
        spec_text = SPEC_PATH.read_text(encoding="utf-8")

        for package in ("torch", "transformers", "onnxruntime", "rapidocr", "pytest"):
            with self.subTest(package=package):
                self.assertIn(f'"{package}"', spec_text)
        self.assertIn("excludes=PRODUCTION_EXCLUDES", spec_text)
        self.assertIn("EXCLUDED_METADATA_PREFIXES", spec_text)

    def test_required_provider_neutral_visual_modules_are_frozen(self):
        spec_text = SPEC_PATH.read_text(encoding="utf-8")

        for module in (
            "visual_understanding_contract",
            "visual_evidence",
            "visual_candidate_detection",
            "visual_understanding_pipeline",
            "visual_understanding_store",
            "visual_understanding_export",
            "visual_capability_pack",
        ):
            with self.subTest(module=module):
                self.assertIn(f'"{module}"', spec_text)

    def test_local_visual_binaries_models_and_evaluation_are_not_frozen(self):
        spec_text = SPEC_PATH.read_text(encoding="utf-8")

        for forbidden in (
            "local_visual_runtime",
            "local_visual_understanding_provider",
            "visual_understanding_evaluation",
            "llama-server",
            ".gguf",
            "mmproj",
        ):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(f'"{forbidden}"', spec_text)

    def test_spec_does_not_recursively_collect_every_paddlex_module(self):
        spec_text = SPEC_PATH.read_text(encoding="utf-8")

        self.assertNotIn('collect_submodules("paddlex")', spec_text)

    def test_spec_retains_required_paddlex_resources(self):
        spec_text = SPEC_PATH.read_text(encoding="utf-8")

        self.assertIn('collect_data_files("paddlex", include_py_files=False)', spec_text)
        self.assertIn('collect_dynamic_libs("paddlex")', spec_text)


if __name__ == "__main__":
    unittest.main()
