"""Isolated lifecycle adapter for a packaged local llama.cpp sidecar."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import json
from pathlib import Path
import secrets
import socket
import subprocess
import sys
from time import monotonic, sleep
from types import MappingProxyType
from typing import Any, Callable, Mapping
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from visual_capability_pack import (
    VisualCapabilityPackAvailability,
    VisualCapabilityPackReadiness,
    VisualPackIntegrityState,
    VisualPackReadinessState,
)


LOOPBACK_HOST = "127.0.0.1"
HEALTH_ENDPOINT = "/health"
LOCAL_VISUAL_CONTEXT_SIZE = 8192
LOCAL_VISUAL_PARALLEL_SLOTS = 1


class LocalVisualRuntimeState(str, Enum):
    STOPPED = "stopped"
    STARTING = "starting"
    READY = "ready"
    FAILED = "failed"
    STOPPING = "stopping"


class LocalVisualRuntimeFailure(str, Enum):
    INVALID_PACK = "invalid_pack"
    RUNTIME_MISSING = "runtime_executable_missing"
    PROCESS_START_FAILED = "process_start_failed"
    PROCESS_EXITED = "process_exited_before_ready"
    READINESS_TIMEOUT = "readiness_timeout"
    AUTHENTICATION_FAILED = "authentication_failed"
    PORT_UNAVAILABLE = "port_unavailable"
    RUNTIME_UNAVAILABLE = "runtime_unavailable"
    REQUEST_TIMEOUT = "request_timeout"
    HTTP_ERROR = "http_error"
    SHUTDOWN_FAILED = "shutdown_failed"


class LocalVisualRuntimeError(RuntimeError):
    """Safe categorized sidecar failure that never includes launch secrets."""

    def __init__(self, category: LocalVisualRuntimeFailure, message: str) -> None:
        super().__init__(message)
        self.category = category


@dataclass(frozen=True)
class LocalVisualRuntimeStatus:
    """Safe immutable lifecycle snapshot without token or raw command exposure."""

    state: LocalVisualRuntimeState
    pack_id: str
    pack_version: str
    runtime_family: str
    runtime_version: str
    backend_declared: str
    host: str
    port: int | None
    process_id: int | None
    exit_code: int | None
    runtime_metadata: Mapping[str, Any]

    def __post_init__(self) -> None:
        object.__setattr__(self, "runtime_metadata", MappingProxyType(dict(self.runtime_metadata)))


def select_loopback_port() -> int:
    """Ask Windows/the OS for one currently available nonprivileged loopback port."""

    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
            listener.bind((LOOPBACK_HOST, 0))
            port = int(listener.getsockname()[1])
    except OSError as error:
        raise LocalVisualRuntimeError(
            LocalVisualRuntimeFailure.PORT_UNAVAILABLE,
            "A local loopback port could not be selected for visual understanding.",
        ) from error
    if port < 1024:
        raise LocalVisualRuntimeError(
            LocalVisualRuntimeFailure.PORT_UNAVAILABLE,
            "The selected local runtime port was not usable.",
        )
    return port


def build_llama_server_command(
    pack: VisualCapabilityPackAvailability,
    *,
    port: int,
    authentication_token: str,
) -> tuple[str, ...]:
    """Build one pinned local-only llama-server argument array from verified pack paths."""

    if not isinstance(pack, VisualCapabilityPackAvailability):
        raise ValueError("pack must be a VisualCapabilityPackAvailability.")
    if not isinstance(port, int) or isinstance(port, bool) or port < 1024 or port > 65535:
        raise ValueError("port must be a nonprivileged TCP port.")
    if not isinstance(authentication_token, str) or len(authentication_token) < 32:
        raise ValueError("authentication_token must be an unpredictable session token.")
    return (
        str(pack.runtime_executable),
        "--model", str(pack.model_file),
        "--mmproj", str(pack.projector_file),
        "--host", LOOPBACK_HOST,
        "--port", str(port),
        "--api-key", authentication_token,
        "--no-webui",
        "--ctx-size", str(LOCAL_VISUAL_CONTEXT_SIZE),
        "--parallel", str(LOCAL_VISUAL_PARALLEL_SLOTS),
        "--no-cont-batching",
    )


def _windows_creation_flags() -> int:
    return int(getattr(subprocess, "CREATE_NO_WINDOW", 0)) if sys.platform == "win32" else 0


def _create_command_safe_token(token_factory: Callable[..., str]) -> str:
    """Create a strong token that cannot be parsed as a following CLI option."""

    for _ in range(8):
        token = token_factory(48)
        if isinstance(token, str) and len(token) >= 32 and not token.startswith("-"):
            return token
    raise LocalVisualRuntimeError(
        LocalVisualRuntimeFailure.RUNTIME_UNAVAILABLE,
        "A secure local runtime session could not be created.",
    )


class LocalVisualRuntime:
    """Own one authenticated loopback-only sidecar process for a verified pack."""

    def __init__(
        self,
        pack: VisualCapabilityPackAvailability,
        readiness: VisualCapabilityPackReadiness,
        *,
        startup_timeout: float = 120.0,
        poll_interval: float = 0.2,
        shutdown_timeout: float = 5.0,
        process_factory: Callable[..., Any] = subprocess.Popen,
        opener: Callable[..., Any] = urlopen,
        port_selector: Callable[[], int] = select_loopback_port,
        token_factory: Callable[..., str] = secrets.token_urlsafe,
        clock: Callable[[], float] = monotonic,
        sleeper: Callable[[float], None] = sleep,
    ) -> None:
        if not isinstance(pack, VisualCapabilityPackAvailability):
            raise ValueError("pack must be a VisualCapabilityPackAvailability.")
        if not isinstance(readiness, VisualCapabilityPackReadiness):
            raise ValueError("readiness must be a VisualCapabilityPackReadiness.")
        if (readiness.pack_id, readiness.pack_version, readiness.provider_id) != (
            pack.pack_id, pack.pack_version, pack.provider_id,
        ):
            raise ValueError("readiness does not describe the selected capability pack.")
        if readiness.state is VisualPackReadinessState.NOT_READY or not readiness.hashes_verified:
            raise LocalVisualRuntimeError(
                LocalVisualRuntimeFailure.INVALID_PACK,
                "The local visual-understanding pack has not passed full integrity preflight.",
            )
        if any(state is not VisualPackIntegrityState.VERIFIED for state in (
            readiness.runtime_integrity, readiness.model_integrity, readiness.projector_integrity,
        )):
            raise LocalVisualRuntimeError(
                LocalVisualRuntimeFailure.INVALID_PACK,
                "The local visual-understanding runtime and model files are not verified.",
            )
        for value, name in (
            (startup_timeout, "startup_timeout"),
            (poll_interval, "poll_interval"),
            (shutdown_timeout, "shutdown_timeout"),
        ):
            if isinstance(value, bool) or not isinstance(value, (int, float)) or value <= 0:
                raise ValueError(f"{name} must be a positive number.")
        self.pack = pack
        self.readiness = readiness
        self.startup_timeout = float(startup_timeout)
        self.poll_interval = float(poll_interval)
        self.shutdown_timeout = float(shutdown_timeout)
        self._process_factory = process_factory
        self._opener = opener
        self._port_selector = port_selector
        self._token_factory = token_factory
        self._clock = clock
        self._sleeper = sleeper
        self._process = None
        self._port: int | None = None
        self._authentication_token: str | None = None
        self._state = LocalVisualRuntimeState.STOPPED
        self._exit_code: int | None = None
        self._runtime_metadata: dict[str, Any] = {}

    @property
    def state(self) -> LocalVisualRuntimeState:
        return self._state

    @property
    def status(self) -> LocalVisualRuntimeStatus:
        process_id = getattr(self._process, "pid", None) if self._process is not None else None
        return LocalVisualRuntimeStatus(
            self._state,
            self.pack.pack_id,
            self.pack.pack_version,
            self.pack.runtime_family,
            self.pack.runtime_version,
            self.pack.runtime_backend,
            LOOPBACK_HOST,
            self._port,
            process_id,
            self._exit_code,
            self._runtime_metadata,
        )

    @property
    def base_url(self) -> str:
        if self._port is None:
            raise LocalVisualRuntimeError(
                LocalVisualRuntimeFailure.RUNTIME_UNAVAILABLE,
                "The local visual-understanding runtime has not been started.",
            )
        return f"http://{LOOPBACK_HOST}:{self._port}"

    def post_json(
        self,
        endpoint: str,
        payload: Mapping[str, Any],
        *,
        timeout: float,
        maximum_response_bytes: int = 4 * 1024 * 1024,
    ) -> dict[str, Any]:
        """POST bounded JSON to this ready authenticated loopback sidecar only."""

        if self._state is not LocalVisualRuntimeState.READY or self._authentication_token is None:
            raise LocalVisualRuntimeError(
                LocalVisualRuntimeFailure.RUNTIME_UNAVAILABLE,
                "The local visual-understanding runtime is not ready.",
            )
        if (
            not isinstance(endpoint, str)
            or not endpoint.startswith("/")
            or endpoint.startswith("//")
            or "://" in endpoint
        ):
            raise ValueError("endpoint must be one local absolute-path reference.")
        if not isinstance(payload, Mapping):
            raise ValueError("payload must be a JSON object.")
        if isinstance(timeout, bool) or not isinstance(timeout, (int, float)) or timeout <= 0:
            raise ValueError("timeout must be a positive number.")
        if (
            not isinstance(maximum_response_bytes, int)
            or isinstance(maximum_response_bytes, bool)
            or maximum_response_bytes < 1
        ):
            raise ValueError("maximum_response_bytes must be a positive integer.")
        encoded = json.dumps(payload, ensure_ascii=False, allow_nan=False).encode("utf-8")
        request = Request(
            f"{self.base_url}{endpoint}",
            data=encoded,
            headers={
                "Authorization": f"Bearer {self._authentication_token}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with self._opener(request, timeout=float(timeout)) as response:
                body = response.read(maximum_response_bytes + 1)
        except HTTPError as error:
            if error.code in (401, 403):
                raise LocalVisualRuntimeError(
                    LocalVisualRuntimeFailure.AUTHENTICATION_FAILED,
                    "The local visual-understanding runtime rejected session authentication.",
                ) from error
            raise LocalVisualRuntimeError(
                LocalVisualRuntimeFailure.HTTP_ERROR,
                "The local visual-understanding runtime request failed.",
            ) from error
        except (TimeoutError, socket.timeout) as error:
            self._recover_after_request_timeout()
            raise LocalVisualRuntimeError(
                LocalVisualRuntimeFailure.REQUEST_TIMEOUT,
                "The local visual-understanding runtime request timed out.",
            ) from error
        except (URLError, ConnectionError, OSError) as error:
            raise LocalVisualRuntimeError(
                LocalVisualRuntimeFailure.RUNTIME_UNAVAILABLE,
                "The local visual-understanding runtime request was unavailable.",
            ) from error
        if len(body) > maximum_response_bytes:
            raise LocalVisualRuntimeError(
                LocalVisualRuntimeFailure.HTTP_ERROR,
                "The local visual-understanding runtime response exceeded the safe size limit.",
            )
        try:
            value = json.loads(body.decode("utf-8"), parse_constant=lambda value: (_ for _ in ()).throw(
                ValueError(f"Unsupported JSON constant: {value}")
            ))
        except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as error:
            raise LocalVisualRuntimeError(
                LocalVisualRuntimeFailure.HTTP_ERROR,
                "The local visual-understanding runtime returned an invalid response envelope.",
            ) from error
        if not isinstance(value, dict):
            raise LocalVisualRuntimeError(
                LocalVisualRuntimeFailure.HTTP_ERROR,
                "The local visual-understanding runtime returned an invalid response envelope.",
            )
        return value

    def _recover_after_request_timeout(self) -> None:
        """Discard the occupied sidecar and restore a fresh ready single-slot runtime."""

        try:
            self.stop()
            self.start()
            self.wait_until_ready()
        except (LocalVisualRuntimeError, OSError, subprocess.SubprocessError):
            self._state = LocalVisualRuntimeState.FAILED
            self._reap_failed_process()

    def safe_diagnostic_summary(self) -> str:
        """Return bounded lifecycle information without credentials or source evidence."""

        status = self.status
        return (
            f"Local visual runtime state={status.state.value}; pack={status.pack_id}; "
            f"backend={status.backend_declared}; host={status.host}; port={status.port or 'unselected'}"
        )

    def start(self) -> LocalVisualRuntimeStatus:
        """Launch the verified executable without waiting for model readiness."""

        if self._state is not LocalVisualRuntimeState.STOPPED:
            raise LocalVisualRuntimeError(
                LocalVisualRuntimeFailure.RUNTIME_UNAVAILABLE,
                "The local visual-understanding runtime is already active or has failed.",
            )
        if not self.pack.runtime_executable.is_file():
            self._state = LocalVisualRuntimeState.FAILED
            raise LocalVisualRuntimeError(
                LocalVisualRuntimeFailure.RUNTIME_MISSING,
                "The verified local visual runtime executable is no longer available.",
            )
        self._port = self._port_selector()
        if not isinstance(self._port, int) or self._port < 1024 or self._port > 65535:
            self._state = LocalVisualRuntimeState.FAILED
            raise LocalVisualRuntimeError(
                LocalVisualRuntimeFailure.PORT_UNAVAILABLE,
                "The selected local runtime port was not usable.",
            )
        try:
            self._authentication_token = _create_command_safe_token(self._token_factory)
        except LocalVisualRuntimeError:
            self._state = LocalVisualRuntimeState.FAILED
            self._authentication_token = None
            raise
        command = build_llama_server_command(
            self.pack,
            port=self._port,
            authentication_token=self._authentication_token,
        )
        self._state = LocalVisualRuntimeState.STARTING
        try:
            self._process = self._process_factory(
                command,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                shell=False,
                creationflags=_windows_creation_flags(),
            )
        except (OSError, ValueError) as error:
            self._state = LocalVisualRuntimeState.FAILED
            self._authentication_token = None
            raise LocalVisualRuntimeError(
                LocalVisualRuntimeFailure.PROCESS_START_FAILED,
                "The local visual-understanding runtime could not be started.",
            ) from error
        return self.status

    def _reap_failed_process(self) -> None:
        process = self._process
        if process is None:
            return
        try:
            if process.poll() is None:
                process.kill()
            self._exit_code = process.wait(timeout=self.shutdown_timeout)
        except (OSError, subprocess.SubprocessError):
            self._exit_code = process.poll()
        finally:
            self._process = None
            self._authentication_token = None

    def _startup_failure(
        self,
        category: LocalVisualRuntimeFailure,
        message: str,
    ) -> LocalVisualRuntimeError:
        self._state = LocalVisualRuntimeState.FAILED
        self._reap_failed_process()
        return LocalVisualRuntimeError(category, message)

    def wait_until_ready(self) -> LocalVisualRuntimeStatus:
        """Poll the authenticated loopback health endpoint until ready or finite failure."""

        if self._state is not LocalVisualRuntimeState.STARTING or self._process is None:
            raise LocalVisualRuntimeError(
                LocalVisualRuntimeFailure.RUNTIME_UNAVAILABLE,
                "The local visual-understanding runtime is not starting.",
            )
        deadline = self._clock() + self.startup_timeout
        while self._clock() < deadline:
            exit_code = self._process.poll()
            if exit_code is not None:
                self._exit_code = exit_code
                self._process.wait(timeout=self.shutdown_timeout)
                self._process = None
                self._authentication_token = None
                self._state = LocalVisualRuntimeState.FAILED
                raise LocalVisualRuntimeError(
                    LocalVisualRuntimeFailure.PROCESS_EXITED,
                    f"The local visual-understanding runtime exited before readiness (exit code {exit_code}).",
                )
            request = Request(
                f"{self.base_url}{HEALTH_ENDPOINT}",
                headers={"Authorization": f"Bearer {self._authentication_token}"},
                method="GET",
            )
            try:
                with self._opener(request, timeout=min(self.poll_interval, 1.0)) as response:
                    payload = response.read(4096)
                    if response.read(1):
                        raise ValueError("health response exceeded limit")
                data = json.loads(payload.decode("utf-8"))
                if isinstance(data, dict) and data.get("status") == "ok":
                    backend = data.get("backend")
                    if isinstance(backend, str) and backend.strip() and len(backend) <= 80:
                        self._runtime_metadata["backend_reported"] = backend
                    self._state = LocalVisualRuntimeState.READY
                    return self.status
                if not isinstance(data, dict) or data.get("status") not in {"loading", "no slot available"}:
                    raise self._startup_failure(
                        LocalVisualRuntimeFailure.RUNTIME_UNAVAILABLE,
                        "The local visual-understanding runtime returned an invalid readiness response.",
                    )
            except HTTPError as error:
                if error.code in (401, 403):
                    raise self._startup_failure(
                        LocalVisualRuntimeFailure.AUTHENTICATION_FAILED,
                        "The local visual-understanding runtime rejected session authentication.",
                    ) from error
                if error.code not in (429, 503):
                    raise self._startup_failure(
                        LocalVisualRuntimeFailure.RUNTIME_UNAVAILABLE,
                        "The local visual-understanding runtime readiness endpoint was unavailable.",
                    ) from error
            except (URLError, TimeoutError, ConnectionError, OSError):
                pass
            except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as error:
                raise self._startup_failure(
                    LocalVisualRuntimeFailure.RUNTIME_UNAVAILABLE,
                    "The local visual-understanding runtime returned an invalid readiness response.",
                ) from error
            self._sleeper(self.poll_interval)
        raise self._startup_failure(
            LocalVisualRuntimeFailure.READINESS_TIMEOUT,
            "The local visual-understanding runtime did not become ready before the startup timeout.",
        )

    def stop(self) -> LocalVisualRuntimeStatus:
        """Idempotently terminate, forcibly stop if needed, and reap the sidecar."""

        if self._process is None:
            if self._state is not LocalVisualRuntimeState.FAILED:
                self._state = LocalVisualRuntimeState.STOPPED
            self._authentication_token = None
            return self.status
        process = self._process
        self._state = LocalVisualRuntimeState.STOPPING
        try:
            if process.poll() is None:
                process.terminate()
                try:
                    self._exit_code = process.wait(timeout=self.shutdown_timeout)
                except subprocess.TimeoutExpired:
                    process.kill()
                    self._exit_code = process.wait(timeout=self.shutdown_timeout)
            else:
                self._exit_code = process.wait(timeout=self.shutdown_timeout)
        except (OSError, subprocess.SubprocessError) as error:
            try:
                process.kill()
                self._exit_code = process.wait(timeout=self.shutdown_timeout)
            except (OSError, subprocess.SubprocessError):
                self._state = LocalVisualRuntimeState.FAILED
                raise LocalVisualRuntimeError(
                    LocalVisualRuntimeFailure.SHUTDOWN_FAILED,
                    "The local visual-understanding runtime could not be stopped cleanly.",
                ) from error
        finally:
            if process.poll() is not None:
                self._process = None
                self._authentication_token = None
        self._state = LocalVisualRuntimeState.STOPPED
        return self.status

    def __enter__(self) -> "LocalVisualRuntime":
        self.start()
        self.wait_until_ready()
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> bool:
        self.stop()
        return False
