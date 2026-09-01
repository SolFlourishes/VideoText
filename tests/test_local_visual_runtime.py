"""Model-free lifecycle and security tests for the local llama.cpp sidecar adapter."""

from dataclasses import FrozenInstanceError
import hashlib
import json
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import Mock, patch


sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from local_visual_runtime import (
    LOCAL_VISUAL_CONTEXT_SIZE,
    LOCAL_VISUAL_PARALLEL_SLOTS,
    LOOPBACK_HOST,
    LocalVisualRuntime,
    LocalVisualRuntimeError,
    LocalVisualRuntimeFailure,
    LocalVisualRuntimeState,
    build_llama_server_command,
)
from visual_capability_pack import (
    CAPABILITY_PACK_SCHEMA,
    CAPABILITY_PACK_SCHEMA_VERSION,
    CURRENT_VISUAL_PROMPT_SCHEMA_REVISION,
    VISUAL_CAPABILITY,
    VISUAL_PACK_MANIFEST_FILENAME,
    VisualPackReadinessState,
    check_visual_capability_pack_readiness,
    load_visual_capability_pack_manifest,
)


FAKE_SERVER_SOURCE = r'''import argparse
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import sys
import time

parser = argparse.ArgumentParser()
parser.add_argument("--model", required=True)
parser.add_argument("--mmproj", required=True)
parser.add_argument("--host", required=True)
parser.add_argument("--port", required=True, type=int)
parser.add_argument("--api-key", required=True)
parser.add_argument("--no-webui", action="store_true")
parser.add_argument("--ctx-size")
parser.add_argument("--parallel")
parser.add_argument("--no-cont-batching", action="store_true")
parser.add_argument("--fake-mode", default="ready")
args = parser.parse_args()
if args.fake_mode == "early-exit":
    sys.exit(7)
started = time.monotonic()

class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass
    def do_GET(self):
        if self.path != "/health":
            self.send_response(404); self.end_headers(); return
        if args.fake_mode == "auth-reject" or self.headers.get("Authorization") != "Bearer " + args.api_key:
            self.send_response(401); self.end_headers(); return
        status = "ok"
        if args.fake_mode == "timeout" or (args.fake_mode == "delayed" and time.monotonic() - started < 0.3):
            status = "loading"
        payload = json.dumps({"status": status, "backend": "fake-cpu"}).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

ThreadingHTTPServer((args.host, args.port), Handler).serve_forever()
'''


class RecordingFakeProcessFactory:
    def __init__(self, script, mode="ready"):
        self.script = script
        self.mode = mode
        self.calls = []
        self.processes = []

    def __call__(self, command, **kwargs):
        self.calls.append((tuple(command), dict(kwargs)))
        actual = [sys.executable, str(self.script), *command[1:], "--fake-mode", self.mode]
        process = subprocess.Popen(actual, **kwargs)
        self.processes.append(process)
        return process


class LocalVisualRuntimeTests(unittest.TestCase):
    def setUp(self):
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary_directory.cleanup)
        self.root = Path(self.temporary_directory.name).resolve()
        self.script = self.root / "fake_llama_server.py"
        self.script.write_text(FAKE_SERVER_SOURCE, encoding="utf-8")

    def make_pack(self, *, backend="cpu"):
        pack_root = self.root / f"pack-{backend}-{time.monotonic_ns()}"
        runtime = pack_root / "runtime" / "llama-server.exe"
        model = pack_root / "models" / "model.gguf"
        projector = pack_root / "models" / "mmproj.gguf"
        notice = pack_root / "LICENSES" / "NOTICE.md"
        contents = {
            runtime: b"synthetic verified executable",
            model: b"synthetic model; never loaded",
            projector: b"synthetic projector; never loaded",
            notice: b"synthetic notice",
        }
        for path, content in contents.items():
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(content)
        relative = lambda path: path.relative_to(pack_root).as_posix()
        document = {
            "schema": CAPABILITY_PACK_SCHEMA,
            "schema_version": CAPABILITY_PACK_SCHEMA_VERSION,
            "capability": VISUAL_CAPABILITY,
            "pack_id": f"fake-{backend}",
            "pack_version": "1.0.0",
            "provider_id": "local-llama-cpp-vision",
            "runtime": {
                "family": "llama.cpp", "version": "fake-1", "backend": backend,
                "executable": relative(runtime),
            },
            "model": {
                "id": "fake-vlm", "family": "fake", "revision": "test-revision",
                "model_file": relative(model), "projector_file": relative(projector),
                "license": "MIT", "source_repository": "local:test",
                "redistribution_provenance": "Synthetic test fixture.",
            },
            "supported_prompt_schema_revisions": [CURRENT_VISUAL_PROMPT_SCHEMA_REVISION],
            "supported_image_media_types": ["image/png"],
            "minimum_videotext_version": "1.7.2",
            "network_required": False,
            "files": [
                {"path": relative(path), "sha256": hashlib.sha256(content).hexdigest()}
                for path, content in contents.items()
            ],
            "license_notice_paths": [relative(notice)],
        }
        manifest = pack_root / VISUAL_PACK_MANIFEST_FILENAME
        manifest.write_text(json.dumps(document), encoding="utf-8")
        pack = load_visual_capability_pack_manifest(manifest)
        readiness = check_visual_capability_pack_readiness(
            pack, requested_prompt_schema=CURRENT_VISUAL_PROMPT_SCHEMA_REVISION
        )
        self.assertIn(readiness.state, (VisualPackReadinessState.READY, VisualPackReadinessState.PARTIAL))
        return pack, readiness

    def runtime(self, mode="ready", *, backend="cpu", **kwargs):
        pack, readiness = self.make_pack(backend=backend)
        factory = RecordingFakeProcessFactory(self.script, mode)
        runtime = LocalVisualRuntime(
            pack,
            readiness,
            process_factory=factory,
            startup_timeout=kwargs.pop("startup_timeout", 10.0),
            poll_interval=kwargs.pop("poll_interval", 0.05),
            shutdown_timeout=kwargs.pop("shutdown_timeout", 1.0),
            **kwargs,
        )
        return runtime, factory

    def assert_processes_stopped(self, factory):
        for process in factory.processes:
            process.poll()
            self.assertIsNotNone(process.returncode)

    def test_successful_authenticated_loopback_start_and_stop(self):
        runtime, factory = self.runtime()

        starting = runtime.start()
        ready = runtime.wait_until_ready()

        self.assertEqual(LocalVisualRuntimeState.STARTING, starting.state)
        self.assertEqual(LocalVisualRuntimeState.READY, ready.state)
        self.assertEqual(LOOPBACK_HOST, ready.host)
        self.assertGreaterEqual(ready.port, 1024)
        self.assertEqual("fake-cpu", ready.runtime_metadata["backend_reported"])
        runtime.stop()
        self.assertEqual(LocalVisualRuntimeState.STOPPED, runtime.state)
        self.assert_processes_stopped(factory)

    def test_command_uses_verified_paths_loopback_auth_array_and_no_shell(self):
        tokens = []
        def token_factory(_bytes):
            token = "token-" + str(len(tokens)) + "-" + "x" * 40
            tokens.append(token)
            return token
        runtime, factory = self.runtime(token_factory=token_factory)

        runtime.start()
        command, options = factory.calls[0]

        self.assertEqual(str(runtime.pack.runtime_executable), command[0])
        self.assertEqual(str(runtime.pack.model_file), command[command.index("--model") + 1])
        self.assertEqual(str(runtime.pack.projector_file), command[command.index("--mmproj") + 1])
        self.assertEqual(LOOPBACK_HOST, command[command.index("--host") + 1])
        self.assertEqual(tokens[0], command[command.index("--api-key") + 1])
        self.assertIn("--no-webui", command)
        self.assertEqual(str(LOCAL_VISUAL_CONTEXT_SIZE), command[command.index("--ctx-size") + 1])
        self.assertEqual(str(LOCAL_VISUAL_PARALLEL_SLOTS), command[command.index("--parallel") + 1])
        self.assertIn("--no-cont-batching", command)
        self.assertNotIn("-hf", command)
        self.assertNotIn("--model-url", command)
        self.assertIs(options["shell"], False)
        self.assertEqual(subprocess.DEVNULL, options["stdout"])
        self.assertEqual(subprocess.DEVNULL, options["stderr"])
        runtime.stop()

    def test_port_and_token_are_new_for_every_launch_and_never_persisted(self):
        runtime, factory = self.runtime()
        runtime.start()
        first_command = factory.calls[-1][0]
        first_token = first_command[first_command.index("--api-key") + 1]
        first_port = int(first_command[first_command.index("--port") + 1])
        runtime.stop()
        runtime.start()
        second_command = factory.calls[-1][0]
        second_token = second_command[second_command.index("--api-key") + 1]
        second_port = int(second_command[second_command.index("--port") + 1])

        self.assertNotEqual(first_token, second_token)
        self.assertGreaterEqual(first_port, 1024)
        self.assertGreaterEqual(second_port, 1024)
        self.assertNotIn(first_token, runtime.pack.manifest_path.read_text(encoding="utf-8"))
        self.assertNotIn(second_token, runtime.pack.manifest_path.read_text(encoding="utf-8"))
        runtime.stop()

    def test_delayed_readiness_is_polled_until_ready(self):
        runtime, factory = self.runtime("delayed")
        started = time.monotonic()
        runtime.start()
        runtime.wait_until_ready()

        self.assertGreaterEqual(time.monotonic() - started, 0.2)
        self.assertEqual(LocalVisualRuntimeState.READY, runtime.state)
        runtime.stop()
        self.assert_processes_stopped(factory)

    def test_timeout_is_safe_categorized_and_reaps_process(self):
        runtime, factory = self.runtime("timeout", startup_timeout=0.25)
        runtime.start()

        with self.assertRaises(LocalVisualRuntimeError) as caught:
            runtime.wait_until_ready()

        self.assertEqual(LocalVisualRuntimeFailure.READINESS_TIMEOUT, caught.exception.category)
        self.assertEqual(LocalVisualRuntimeState.FAILED, runtime.state)
        self.assertNotIn("api-key", str(caught.exception).lower())
        self.assert_processes_stopped(factory)

    def test_early_exit_is_categorized_and_reaped(self):
        runtime, factory = self.runtime("early-exit")
        runtime.start()

        with self.assertRaises(LocalVisualRuntimeError) as caught:
            runtime.wait_until_ready()

        self.assertEqual(LocalVisualRuntimeFailure.PROCESS_EXITED, caught.exception.category)
        self.assertEqual(7, runtime.status.exit_code)
        self.assert_processes_stopped(factory)

    def test_authentication_rejection_is_categorized_without_token_disclosure(self):
        token = "secret-authentication-token-" + "z" * 40
        runtime, factory = self.runtime("auth-reject", token_factory=lambda _bytes: token)
        runtime.start()

        with self.assertRaises(LocalVisualRuntimeError) as caught:
            runtime.wait_until_ready()

        self.assertEqual(LocalVisualRuntimeFailure.AUTHENTICATION_FAILED, caught.exception.category)
        self.assertNotIn(token, str(caught.exception))
        self.assertNotIn(token, runtime.safe_diagnostic_summary())
        self.assert_processes_stopped(factory)

    def test_context_manager_and_exception_cleanup(self):
        runtime, factory = self.runtime()
        with runtime:
            self.assertEqual(LocalVisualRuntimeState.READY, runtime.state)
        self.assertEqual(LocalVisualRuntimeState.STOPPED, runtime.state)
        self.assert_processes_stopped(factory)

        second, second_factory = self.runtime()
        with self.assertRaisesRegex(RuntimeError, "caller failure"):
            with second:
                raise RuntimeError("caller failure")
        self.assertEqual(LocalVisualRuntimeState.STOPPED, second.state)
        self.assert_processes_stopped(second_factory)

    def test_option_like_authentication_token_is_regenerated(self):
        tokens = iter(("-" + "x" * 47, "safe-" + "y" * 43))
        runtime, factory = self.runtime(token_factory=lambda length: next(tokens))
        runtime.start()
        self.addCleanup(runtime.stop)
        command = factory.calls[0][0]
        self.assertEqual("safe-" + "y" * 43, command[command.index("--api-key") + 1])

    def test_repeated_stop_is_idempotent(self):
        runtime, factory = self.runtime()
        runtime.start(); runtime.wait_until_ready()

        first = runtime.stop()
        second = runtime.stop()

        self.assertEqual(LocalVisualRuntimeState.STOPPED, first.state)
        self.assertEqual(LocalVisualRuntimeState.STOPPED, second.state)
        self.assert_processes_stopped(factory)

    def test_forced_stop_after_hung_graceful_termination(self):
        pack, readiness = self.make_pack()
        process = Mock(pid=99)
        process.poll.side_effect = [None, None, 9]
        process.wait.side_effect = [subprocess.TimeoutExpired("fake", 0.01), 9]
        runtime = LocalVisualRuntime(
            pack, readiness, process_factory=lambda *args, **kwargs: process,
            port_selector=lambda: 12345, token_factory=lambda _bytes: "x" * 40,
            shutdown_timeout=0.01,
        )
        runtime.start()

        status = runtime.stop()

        process.terminate.assert_called_once()
        process.kill.assert_called_once()
        self.assertEqual(LocalVisualRuntimeState.STOPPED, status.state)

    def test_process_start_failure_and_missing_runtime_leave_no_child(self):
        pack, readiness = self.make_pack()
        runtime = LocalVisualRuntime(
            pack, readiness,
            process_factory=Mock(side_effect=OSError("unsafe raw details")),
            port_selector=lambda: 12345,
        )
        with self.assertRaises(LocalVisualRuntimeError) as caught:
            runtime.start()
        self.assertEqual(LocalVisualRuntimeFailure.PROCESS_START_FAILED, caught.exception.category)
        self.assertEqual(LocalVisualRuntimeState.FAILED, runtime.state)
        self.assertIsNone(runtime.status.process_id)

        pack.runtime_executable.unlink()
        missing = LocalVisualRuntime(pack, readiness)
        with self.assertRaises(LocalVisualRuntimeError) as caught:
            missing.start()
        self.assertEqual(LocalVisualRuntimeFailure.RUNTIME_MISSING, caught.exception.category)

    def test_manifest_cannot_override_host_and_remote_host_is_never_accepted(self):
        runtime, factory = self.runtime()
        document = json.loads(runtime.pack.manifest_path.read_text(encoding="utf-8"))
        document["runtime"]["host"] = "0.0.0.0"
        runtime.pack.manifest_path.write_text(json.dumps(document), encoding="utf-8")

        runtime.start()
        command = factory.calls[0][0]

        self.assertEqual(LOOPBACK_HOST, command[command.index("--host") + 1])
        self.assertNotIn("0.0.0.0", command)
        runtime.stop()

    def test_declared_backend_is_retained_without_console_parsing(self):
        runtime, factory = self.runtime(backend="cpu-vulkan")
        runtime.start(); status = runtime.wait_until_ready()

        self.assertEqual("cpu-vulkan", status.backend_declared)
        self.assertEqual("fake-cpu", status.runtime_metadata["backend_reported"])
        runtime.stop()
        self.assert_processes_stopped(factory)

    def test_adapter_reads_no_model_runtime_bytes_and_performs_no_inference(self):
        runtime, factory = self.runtime()
        with patch.object(Path, "read_bytes", side_effect=AssertionError("binary content read")) as reader:
            runtime.start(); runtime.wait_until_ready(); runtime.stop()

        reader.assert_not_called()
        self.assert_processes_stopped(factory)
        source = (Path(__file__).resolve().parent.parent / "src" / "local_visual_runtime.py").read_text(
            encoding="utf-8"
        )
        self.assertNotIn("/v1/chat/completions", source)
        self.assertNotIn("shell=True", source)

    def test_status_is_immutable_and_excludes_authentication_token(self):
        token = "private-token-" + "q" * 40
        runtime, factory = self.runtime(token_factory=lambda _bytes: token)
        status = runtime.start()

        self.assertNotIn(token, repr(status))
        self.assertNotIn(token, runtime.safe_diagnostic_summary())
        with self.assertRaises(FrozenInstanceError):
            status.state = LocalVisualRuntimeState.READY
        runtime.stop()
        self.assert_processes_stopped(factory)

    def test_command_builder_rejects_privileged_port(self):
        pack, _ = self.make_pack()
        with self.assertRaisesRegex(ValueError, "nonprivileged"):
            build_llama_server_command(pack, port=80, authentication_token="x" * 40)

    def test_request_timeout_restarts_runtime_and_next_request_succeeds_without_retry(self):
        class Response:
            def __init__(self, value):
                self.body = json.dumps(value).encode("utf-8")
                self.offset = 0
            def __enter__(self): return self
            def __exit__(self, *args): return False
            def read(self, size=-1):
                if size < 0:
                    size = len(self.body) - self.offset
                value = self.body[self.offset:self.offset + size]
                self.offset += len(value)
                return value

        runtime, factory = self.runtime()
        runtime.start(); runtime.wait_until_ready()
        calls = []
        def opener(request, timeout):
            calls.append(request.get_method())
            if request.get_method() == "GET":
                return Response({"status": "ok", "backend": "fake-cpu"})
            if calls.count("POST") == 1:
                raise TimeoutError("occupied generation")
            return Response({"ok": True})
        runtime._opener = opener

        with self.assertRaises(LocalVisualRuntimeError) as caught:
            runtime.post_json("/test", {"request": 1}, timeout=0.01)

        self.assertEqual(LocalVisualRuntimeFailure.REQUEST_TIMEOUT, caught.exception.category)
        self.assertEqual(LocalVisualRuntimeState.READY, runtime.state)
        self.assertEqual({"ok": True}, runtime.post_json("/test", {"request": 2}, timeout=1))
        self.assertEqual(2, calls.count("POST"))
        self.assertEqual(2, len(factory.processes))
        runtime.stop()
        self.assert_processes_stopped(factory)


if __name__ == "__main__":
    unittest.main()
