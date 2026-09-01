"""Focused tests for local visual capability-pack manifests and discovery."""

from dataclasses import FrozenInstanceError
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch


sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from visual_capability_pack import (
    CAPABILITY_PACK_SCHEMA,
    CAPABILITY_PACK_SCHEMA_VERSION,
    CURRENT_VISUAL_PROMPT_SCHEMA_REVISION,
    VISUAL_CAPABILITY,
    VISUAL_PACK_MANIFEST_FILENAME,
    VISUAL_PACK_ROOT_ENVIRONMENT_VARIABLE,
    VisualCapabilityPackAvailability,
    VisualCapabilityPackError,
    VisualPackBackendState,
    VisualPackIntegrityState,
    VisualPackReadinessCategory,
    VisualPackReadinessState,
    check_visual_capability_pack_readiness,
    default_visual_pack_root,
    discover_visual_capability_packs,
    load_visual_capability_pack_manifest,
)


class VisualCapabilityPackTests(unittest.TestCase):
    def setUp(self):
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary_directory.cleanup)
        self.root = Path(self.temporary_directory.name).resolve()

    def manifest(self, pack_id="qwen-vl", **changes):
        value = {
            "schema": CAPABILITY_PACK_SCHEMA,
            "schema_version": CAPABILITY_PACK_SCHEMA_VERSION,
            "capability": VISUAL_CAPABILITY,
            "pack_id": pack_id,
            "pack_version": "1.0.0",
            "provider_id": "local-llama-cpp-vision",
            "runtime": {
                "family": "llama.cpp",
                "version": "b7000",
                "backend": "cpu-vulkan",
                "executable": "runtime/cpu-vulkan/llama-server.exe",
            },
            "model": {
                "id": "Qwen/Qwen2.5-VL-7B-Instruct",
                "family": "qwen2.5-vl",
                "revision": "0123456789abcdef",
                "model_file": "models/model-q4_k_m.gguf",
                "projector_file": "models/mmproj-f16.gguf",
                "license": "Apache-2.0",
                "source_repository": "https://huggingface.co/Qwen/Qwen2.5-VL-7B-Instruct",
                "redistribution_provenance": "Converted from pinned upstream revision.",
            },
            "supported_prompt_schema_revisions": [CURRENT_VISUAL_PROMPT_SCHEMA_REVISION],
            "supported_image_media_types": ["image/png"],
            "minimum_videotext_version": "1.7.0",
            "network_required": False,
            "files": [
                {"path": "runtime/cpu-vulkan/llama-server.exe", "sha256": "a" * 64},
                {"path": "models/model-q4_k_m.gguf", "sha256": "b" * 64},
                {"path": "models/mmproj-f16.gguf", "sha256": "c" * 64},
                {"path": "LICENSES/NOTICE.md", "sha256": "d" * 64},
            ],
            "license_notice_paths": ["LICENSES/NOTICE.md"],
        }
        value.update(changes)
        return value

    def write_pack(self, name="qwen", manifest=None, *, create_files=True):
        pack = self.root / name
        pack.mkdir()
        value = self.manifest(name) if manifest is None else manifest
        path = pack / VISUAL_PACK_MANIFEST_FILENAME
        path.write_text(json.dumps(value), encoding="utf-8")
        if create_files:
            for declaration in value.get("files", ()):
                relative = Path(declaration["path"])
                if relative.is_absolute() or ".." in relative.parts:
                    continue
                target = pack / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(b"test; content is deliberately not hashed")
        return path

    def write_hash_valid_pack(self, name="ready", *, backend="cpu", minimum="1.7.2"):
        value = self.manifest(name, minimum_videotext_version=minimum)
        value["runtime"]["backend"] = backend
        contents = {}
        for index, declaration in enumerate(value["files"]):
            content = (f"synthetic-pack-file-{index}-" * (index + 1)).encode("utf-8")
            declaration["sha256"] = hashlib.sha256(content).hexdigest()
            contents[declaration["path"]] = content
        path = self.write_pack(name, value, create_files=False)
        for relative, content in contents.items():
            target = path.parent / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(content)
        return path

    def test_valid_manifest_returns_complete_immutable_availability(self):
        path = self.write_pack()

        pack = load_visual_capability_pack_manifest(path)

        self.assertIsInstance(pack, VisualCapabilityPackAvailability)
        self.assertTrue(pack.compatible)
        self.assertEqual("llama.cpp", pack.runtime_family)
        self.assertEqual("Qwen/Qwen2.5-VL-7B-Instruct", pack.model_id)
        self.assertFalse(pack.network_required)
        self.assertTrue(pack.runtime_executable.is_file())
        self.assertTrue(pack.model_file.is_relative_to(pack.pack_root))
        self.assertTrue(pack.projector_file.is_relative_to(pack.pack_root))
        self.assertTrue(pack.supports_prompt_schema(CURRENT_VISUAL_PROMPT_SCHEMA_REVISION))
        with self.assertRaises(FrozenInstanceError):
            pack.pack_id = "changed"
        with self.assertRaises(FrozenInstanceError):
            pack.declared_files[0].exists = False

    def test_no_pack_root_is_a_normal_empty_result(self):
        missing = self.root / "not-installed"

        result = discover_visual_capability_packs((missing,))

        self.assertEqual((missing.resolve(),), result.searched_roots)
        self.assertEqual((), result.packs)
        self.assertEqual((), result.issues)

    def test_multiple_valid_packs_are_deterministic(self):
        self.write_pack("z-pack")
        self.write_pack("a-pack")

        result = discover_visual_capability_packs((self.root,))

        self.assertEqual(("a-pack", "z-pack"), tuple(pack.pack_id for pack in result.packs))
        self.assertEqual((), result.issues)

    def test_invalid_pack_does_not_hide_valid_pack(self):
        self.write_pack("valid")
        invalid = self.manifest("invalid", schema="other.schema")
        self.write_pack("invalid", invalid)

        result = discover_visual_capability_packs((self.root,))

        self.assertEqual(("valid",), tuple(pack.pack_id for pack in result.packs))
        self.assertEqual(1, len(result.issues))
        self.assertIn("Unsupported capability-pack schema", result.issues[0].error)

    def test_wrong_schema_unknown_version_wrong_capability_and_missing_fields_rejected(self):
        cases = (
            ({"schema": "wrong"}, "schema"),
            ({"schema_version": "2.0"}, "schema version"),
            ({"capability": "translation"}, "capability"),
        )
        for index, (change, message) in enumerate(cases):
            with self.subTest(change=change):
                path = self.write_pack(f"bad-{index}", self.manifest(**change))
                with self.assertRaisesRegex(VisualCapabilityPackError, message):
                    load_visual_capability_pack_manifest(path)
        missing = self.manifest()
        del missing["model"]
        path = self.write_pack("missing", missing)
        with self.assertRaisesRegex(VisualCapabilityPackError, "missing required"):
            load_visual_capability_pack_manifest(path)

    def test_traversal_absolute_and_symlink_escape_are_rejected(self):
        traversal = self.manifest()
        traversal["runtime"]["executable"] = "../llama-server.exe"
        path = self.write_pack("traversal", traversal)
        with self.assertRaisesRegex(VisualCapabilityPackError, "safe relative"):
            load_visual_capability_pack_manifest(path)

        absolute = self.manifest()
        absolute["model"]["model_file"] = str((self.root / "outside.gguf").resolve())
        path = self.write_pack("absolute", absolute)
        with self.assertRaisesRegex(VisualCapabilityPackError, "safe relative"):
            load_visual_capability_pack_manifest(path)

        if hasattr(os, "symlink"):
            pack = self.root / "symlink"
            pack.mkdir()
            outside = self.root / "outside"
            outside.mkdir()
            try:
                (pack / "models").symlink_to(outside, target_is_directory=True)
            except OSError:
                return
            value = self.manifest("symlink")
            path = pack / VISUAL_PACK_MANIFEST_FILENAME
            path.write_text(json.dumps(value), encoding="utf-8")
            with self.assertRaisesRegex(VisualCapabilityPackError, "escapes"):
                load_visual_capability_pack_manifest(path)

    def test_missing_principal_files_are_reported_without_loading_them(self):
        path = self.write_pack(create_files=False)

        pack = load_visual_capability_pack_manifest(path)

        self.assertFalse(pack.compatible)
        self.assertEqual(5, len(pack.errors))
        self.assertTrue(any("llama-server.exe" in error for error in pack.errors))
        self.assertTrue(any("model-q4_k_m.gguf" in error for error in pack.errors))
        self.assertTrue(any("mmproj-f16.gguf" in error for error in pack.errors))

    def test_malformed_hash_duplicate_files_and_undeclared_principal_rejected(self):
        malformed = self.manifest()
        malformed["files"][0]["sha256"] = "not-a-hash"
        path = self.write_pack("hash", malformed)
        with self.assertRaisesRegex(VisualCapabilityPackError, "SHA-256"):
            load_visual_capability_pack_manifest(path)

        duplicate = self.manifest()
        duplicate["files"].append(dict(duplicate["files"][0]))
        path = self.write_pack("duplicate", duplicate)
        with self.assertRaisesRegex(VisualCapabilityPackError, "Duplicate"):
            load_visual_capability_pack_manifest(path)

        undeclared = self.manifest()
        undeclared["files"] = undeclared["files"][1:]
        path = self.write_pack("undeclared", undeclared)
        with self.assertRaisesRegex(VisualCapabilityPackError, "must be declared"):
            load_visual_capability_pack_manifest(path)

    def test_application_and_prompt_schema_compatibility_are_separate(self):
        value = self.manifest(minimum_videotext_version="1.9.0")
        value["supported_prompt_schema_revisions"] = ["future-prompt-v2"]
        path = self.write_pack(manifest=value)

        pack = load_visual_capability_pack_manifest(path, application_version="1.8.0-dev")

        self.assertFalse(pack.compatible)
        self.assertIn("requires VideoText 1.9.0", pack.errors[0])
        self.assertFalse(pack.supports_prompt_schema(CURRENT_VISUAL_PROMPT_SCHEMA_REVISION))
        self.assertTrue(pack.supports_prompt_schema("future-prompt-v2"))

    def test_network_required_is_descriptive_but_incompatible_with_local_offline_pack(self):
        path = self.write_pack(manifest=self.manifest(network_required=True))

        pack = load_visual_capability_pack_manifest(path)

        self.assertTrue(pack.network_required)
        self.assertFalse(pack.compatible)
        self.assertIn("network access is required", pack.errors[-1])

    def test_default_localappdata_and_explicit_portable_roots(self):
        local = self.root / "LocalAppData"
        expected = local / "VideoText" / "models" / "vision"
        self.assertEqual(expected.resolve(), default_visual_pack_root({"LOCALAPPDATA": str(local)}))

        portable = self.root / "portable-vision-packs"
        pack = portable / "qwen"
        pack.mkdir(parents=True)
        value = self.manifest("portable")
        path = pack / VISUAL_PACK_MANIFEST_FILENAME
        path.write_text(json.dumps(value), encoding="utf-8")
        for declaration in value["files"]:
            target = pack / declaration["path"]
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(b"test")
        environment = {
            "LOCALAPPDATA": str(local),
            VISUAL_PACK_ROOT_ENVIRONMENT_VARIABLE: str(portable),
        }

        self.assertEqual(portable.resolve(), default_visual_pack_root(environment))
        result = discover_visual_capability_packs(environ=environment)
        self.assertEqual(("portable",), tuple(item.pack_id for item in result.packs))

    def test_discovery_has_no_registry_process_network_or_content_hash_side_effects(self):
        self.write_pack()
        module_source = (Path(__file__).resolve().parent.parent / "src" / "visual_capability_pack.py").read_text(
            encoding="utf-8"
        )
        self.assertNotIn("import winreg", module_source)
        self.assertNotIn("import hashlib", module_source)
        self.assertNotIn("import subprocess", module_source)
        with (
            patch("subprocess.Popen") as process,
            patch("socket.create_connection") as network,
            patch("urllib.request.urlopen") as urlopen,
            patch.object(Path, "read_bytes", side_effect=AssertionError("content read")) as read_bytes,
        ):
            result = discover_visual_capability_packs((self.root,))

        self.assertEqual(1, len(result.packs))
        for operation in (process, network, urlopen, read_bytes):
            operation.assert_not_called()

    def test_only_root_or_immediate_pack_manifests_are_discovered(self):
        self.write_pack("direct")
        nested = self.root / "unrelated" / "deep" / "pack"
        nested.mkdir(parents=True)
        (nested / VISUAL_PACK_MANIFEST_FILENAME).write_text(
            json.dumps(self.manifest("nested")), encoding="utf-8"
        )

        result = discover_visual_capability_packs((self.root,))

        self.assertEqual(("direct",), tuple(pack.pack_id for pack in result.packs))

    def readiness(self, path, **kwargs):
        pack = load_visual_capability_pack_manifest(path)
        return check_visual_capability_pack_readiness(
            pack,
            requested_prompt_schema=CURRENT_VISUAL_PROMPT_SCHEMA_REVISION,
            **kwargs,
        )

    def test_fully_ready_cpu_pack_verifies_runtime_model_projector_and_notices(self):
        readiness = self.readiness(self.write_hash_valid_pack())

        self.assertEqual(VisualPackReadinessState.READY, readiness.state)
        self.assertEqual(VisualPackIntegrityState.VERIFIED, readiness.required_files_integrity)
        self.assertEqual(VisualPackIntegrityState.VERIFIED, readiness.runtime_integrity)
        self.assertEqual(VisualPackIntegrityState.VERIFIED, readiness.model_integrity)
        self.assertEqual(VisualPackIntegrityState.VERIFIED, readiness.projector_integrity)
        self.assertEqual(VisualPackBackendState.STRUCTURALLY_READY, readiness.backend_readiness)
        self.assertTrue(readiness.hashes_verified)
        self.assertEqual((), readiness.errors)
        self.assertEqual((), readiness.warnings)
        with self.assertRaises(FrozenInstanceError):
            readiness.state = VisualPackReadinessState.NOT_READY

    def test_each_principal_hash_mismatch_is_categorized_with_safe_hash_evidence(self):
        cases = (
            ("runtime/cpu-vulkan/llama-server.exe", "runtime_integrity"),
            ("models/model-q4_k_m.gguf", "model_integrity"),
            ("models/mmproj-f16.gguf", "projector_integrity"),
        )
        for index, (relative, field) in enumerate(cases):
            with self.subTest(relative=relative):
                path = self.write_hash_valid_pack(f"mismatch-{index}")
                target = path.parent / relative
                target.write_bytes(target.read_bytes() + b"changed")

                readiness = self.readiness(path)

                self.assertEqual(VisualPackReadinessState.NOT_READY, readiness.state)
                self.assertEqual(VisualPackIntegrityState.INVALID, getattr(readiness, field))
                issue = next(item for item in readiness.errors
                             if item.category is VisualPackReadinessCategory.HASH_MISMATCH)
                self.assertEqual(Path(relative), issue.relative_path)
                self.assertRegex(issue.declared_sha256, r"^[0-9a-f]{64}$")
                self.assertRegex(issue.observed_sha256, r"^[0-9a-f]{64}$")

    def test_each_missing_principal_file_is_not_ready_and_categorized(self):
        cases = (
            ("runtime/cpu-vulkan/llama-server.exe", "runtime_integrity"),
            ("models/model-q4_k_m.gguf", "model_integrity"),
            ("models/mmproj-f16.gguf", "projector_integrity"),
        )
        for index, (relative, field) in enumerate(cases):
            with self.subTest(relative=relative):
                path = self.write_hash_valid_pack(f"missing-ready-{index}")
                (path.parent / relative).unlink()
                pack = load_visual_capability_pack_manifest(path)
                self.assertIn(pack, discover_visual_capability_packs((self.root,)).packs)

                readiness = check_visual_capability_pack_readiness(
                    pack, requested_prompt_schema=CURRENT_VISUAL_PROMPT_SCHEMA_REVISION
                )

                self.assertEqual(VisualPackReadinessState.NOT_READY, readiness.state)
                self.assertEqual(VisualPackIntegrityState.MISSING, getattr(readiness, field))
                self.assertIn(VisualPackReadinessCategory.MISSING_FILE,
                              tuple(issue.category for issue in readiness.errors))

    def test_post_discovery_symlink_escape_is_rejected_without_reading_outside(self):
        if not hasattr(os, "symlink"):
            self.skipTest("symbolic links are unavailable")
        path = self.write_hash_valid_pack("post-discovery-link")
        pack = load_visual_capability_pack_manifest(path)
        model = path.parent / "models" / "model-q4_k_m.gguf"
        outside = self.root / "outside.gguf"
        outside.write_bytes(b"outside")
        model.unlink()
        try:
            model.symlink_to(outside)
        except OSError:
            self.skipTest("symbolic links require privileges on this Windows configuration")

        readiness = check_visual_capability_pack_readiness(
            pack, requested_prompt_schema=CURRENT_VISUAL_PROMPT_SCHEMA_REVISION
        )

        self.assertEqual(VisualPackReadinessState.NOT_READY, readiness.state)
        self.assertEqual(VisualPackIntegrityState.INVALID, readiness.model_integrity)
        self.assertIn(VisualPackReadinessCategory.UNSAFE_PATH,
                      tuple(issue.category for issue in readiness.errors))

    def test_prompt_and_media_compatibility_are_request_specific(self):
        path = self.write_hash_valid_pack()
        pack = load_visual_capability_pack_manifest(path)

        prompt = check_visual_capability_pack_readiness(
            pack, requested_prompt_schema="future-prompt-v2"
        )
        media = check_visual_capability_pack_readiness(
            pack,
            requested_prompt_schema=CURRENT_VISUAL_PROMPT_SCHEMA_REVISION,
            requested_image_media_type="image/jpeg",
        )

        self.assertFalse(prompt.prompt_schema_compatible)
        self.assertEqual(VisualPackReadinessCategory.UNSUPPORTED_PROMPT_SCHEMA,
                         prompt.errors[0].category)
        self.assertFalse(media.image_media_compatible)
        self.assertEqual(VisualPackReadinessCategory.UNSUPPORTED_MEDIA_TYPE,
                         media.errors[0].category)

    def test_current_and_future_application_version_behavior_uses_app_release(self):
        current = self.readiness(self.write_hash_valid_pack("current", minimum="1.7.2"))
        future_path = self.write_hash_valid_pack("future", minimum="1.9.0")
        future_pack = load_visual_capability_pack_manifest(future_path)
        future = check_visual_capability_pack_readiness(
            future_pack, requested_prompt_schema=CURRENT_VISUAL_PROMPT_SCHEMA_REVISION
        )

        self.assertTrue(current.application_version_compatible)
        self.assertEqual(VisualPackReadinessState.READY, current.state)
        self.assertFalse(future.application_version_compatible)
        self.assertEqual(VisualPackReadinessState.NOT_READY, future.state)
        self.assertEqual(VisualPackReadinessCategory.INCOMPATIBLE_APP_VERSION,
                         future.errors[0].category)

    def test_vulkan_and_cuda_are_partial_until_runtime_confirmation(self):
        for backend in ("cpu-vulkan", "vulkan", "cuda"):
            with self.subTest(backend=backend):
                readiness = self.readiness(self.write_hash_valid_pack(f"backend-{backend}", backend=backend))

                self.assertEqual(VisualPackReadinessState.PARTIAL, readiness.state)
                self.assertEqual(VisualPackBackendState.RUNTIME_UNCONFIRMED,
                                 readiness.backend_readiness)
                self.assertEqual(VisualPackReadinessCategory.BACKEND_UNCONFIRMED,
                                 readiness.warnings[0].category)

    def test_hash_opt_out_is_explicit_partial_not_silently_ready(self):
        readiness = self.readiness(self.write_hash_valid_pack(), verify_hashes=False)

        self.assertEqual(VisualPackReadinessState.PARTIAL, readiness.state)
        self.assertEqual(VisualPackIntegrityState.UNVERIFIED, readiness.required_files_integrity)
        self.assertFalse(readiness.hashes_verified)
        self.assertEqual(VisualPackReadinessCategory.INTEGRITY_UNVERIFIED,
                         readiness.warnings[0].category)

    def test_large_file_hashing_is_streamed_in_bounded_reads(self):
        path = self.write_hash_valid_pack("streamed")
        model_path = path.parent / "models" / "model-q4_k_m.gguf"
        content = b"x" * (2 * 1024 * 1024 + 123)
        model_path.write_bytes(content)
        document = json.loads(path.read_text(encoding="utf-8"))
        declaration = next(item for item in document["files"] if item["path"].endswith("model-q4_k_m.gguf"))
        declaration["sha256"] = hashlib.sha256(content).hexdigest()
        path.write_text(json.dumps(document), encoding="utf-8")
        reads = []
        original_open = Path.open

        class TrackingReader:
            def __init__(self, wrapped): self.wrapped = wrapped
            def __enter__(self): return self
            def __exit__(self, *args): return self.wrapped.__exit__(*args)
            def read(self, size=-1): reads.append(size); return self.wrapped.read(size)

        def tracking_open(current, mode="r", *args, **kwargs):
            opened = original_open(current, mode, *args, **kwargs)
            return TrackingReader(opened) if current.resolve() == model_path.resolve() and mode == "rb" else opened

        with patch.object(Path, "open", tracking_open):
            readiness = self.readiness(path)

        self.assertEqual(VisualPackReadinessState.READY, readiness.state)
        self.assertGreaterEqual(len(reads), 3)
        self.assertTrue(all(size == 1024 * 1024 for size in reads))

    def test_discovery_remains_hash_free_after_preflight_is_added(self):
        self.write_hash_valid_pack()
        with patch("visual_capability_pack._stream_sha256",
                   side_effect=AssertionError("discovery hashed content")) as hasher:
            result = discover_visual_capability_packs((self.root,))
        self.assertEqual(1, len(result.packs))
        hasher.assert_not_called()

    def test_preflight_starts_no_process_and_performs_no_network_access(self):
        pack = load_visual_capability_pack_manifest(self.write_hash_valid_pack())
        with (
            patch("subprocess.Popen") as process,
            patch("subprocess.run") as run,
            patch("socket.create_connection") as network,
            patch("urllib.request.urlopen") as urlopen,
        ):
            readiness = check_visual_capability_pack_readiness(
                pack, requested_prompt_schema=CURRENT_VISUAL_PROMPT_SCHEMA_REVISION
            )
        self.assertEqual(VisualPackReadinessState.READY, readiness.state)
        for operation in (process, run, network, urlopen):
            operation.assert_not_called()


if __name__ == "__main__":
    unittest.main()
