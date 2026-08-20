"""Per-session Claude Code governance service and fail-open hook entry point.

Claude Code runs every hook in its own short-lived process, so session state cannot
live in the hook. One authenticated loopback service per session owns the runtime,
exactly as the Codex integration does, which keeps authorization strictly before
execution and settlement strictly after it.

Every failure path fails open. A hook that cannot reach its service, cannot parse
its payload, or raises for any reason exits 0 with no output, and Claude Code
proceeds as if MARGINAL were not installed.
"""

from __future__ import annotations

import json
import os
import secrets
import subprocess
import sys
import threading
import time
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from marginal.controls import ActionOutcomeStatus
from marginal.privacy import PrivacyProfile

from ..hookkit.bootstrap import ObserveSession, build_observe_session
from ..hookkit.session import HookSessionRuntime
from ..transport import (
    ConnectionInfo,
    SessionHandler,
    SessionServer,
    connection_filename,
    request_session,
)
from .events import (
    ClaudeCodeHookEvent,
    PostToolUseEvent,
    PostToolUseFailureEvent,
    PreToolUseEvent,
    SessionEvent,
    parse_hook_event,
)
from .normalization import ENGINE, tool_call_end, tool_call_start

DATA_ROOT_VARIABLES = ("CLAUDE_PLUGIN_DATA", "MARGINAL_CLAUDE_CODE_DATA", "PLUGIN_DATA")
_READY_TIMEOUT_SECONDS = 5.0
_SERVERS: dict[tuple[Path, str], tuple[SessionServer, HookSessionRuntime]] = {}


@dataclass(frozen=True, slots=True)
class HookResult:
    """What one hook invocation reports back to Claude Code."""

    exit_code: int
    output: dict[str, Any] | None = None
    warning_code: str = ""


def data_root_from_environment() -> str:
    """Return the first configured plugin data directory, or an empty string."""

    for name in DATA_ROOT_VARIABLES:
        value = os.environ.get(name)
        if value:
            return value
    return ""


def _connection_path(data_root: Path, session_id: str) -> Path:
    return data_root / "sessions" / connection_filename(session_id)


def _bootstrap_path(data_root: Path, session_id: str) -> Path:
    bootstrap_root = data_root / "bootstrap"
    bootstrap_root.mkdir(parents=True, exist_ok=True, mode=0o700)
    if os.name == "posix":
        bootstrap_root.chmod(0o700)
    from ..hookkit.bootstrap import session_hash

    return bootstrap_root / f"{session_hash(session_id)}-{secrets.token_hex(8)}.json"


def _bootstrap_event_payload(event: SessionEvent) -> dict[str, Any]:
    """Keep the service bootstrap free of transcript and unrelated hook fields."""

    return {
        "session_id": event.session_id,
        "cwd": event.cwd,
        "hook_event_name": event.hook_event_name,
        "source": event.source,
    }


def _handler(
    session: HookSessionRuntime,
    *,
    observe: ObserveSession,
    shutdown_event: threading.Event | None = None,
) -> SessionHandler:
    def handle(operation: str, payload: Mapping[str, Any]) -> Mapping[str, Any] | None:
        if operation == "status":
            return {**session.summary(), "workspace_hash": observe.workspace_hash}
        if operation == "close":
            session.close()
            observe.record(
                {
                    "event": "hook_session_end",
                    **{f"summary_{name}": value for name, value in session.summary().items()},
                }
            )
            if shutdown_event is not None:
                threading.Timer(0.05, shutdown_event.set).start()
            return session.summary()

        event = parse_hook_event(payload)
        if operation == "pre" and isinstance(event, PreToolUseEvent):
            started = time.perf_counter_ns()
            decision = session.tool_call_start(tool_call_start(event))
            latency_ms = (time.perf_counter_ns() - started) / 1_000_000
            signal = session.last_no_progress_signal
            observe.record(
                {
                    "event": "hook_decision",
                    **(session.last_action_evidence or {}),
                    "reason_code": decision.reason_code,
                    "recommended": decision.recommended,
                    "recommended_stop": bool(signal and signal.should_recommend_stop),
                    "no_progress_reason_code": signal.reason_code if signal else "",
                    "governance_latency_ms": latency_ms,
                    "enforced": False,
                }
            )
            # Shadow Mode never changes what Claude Code does next.
            return None
        if operation == "post" and isinstance(event, (PostToolUseEvent, PostToolUseFailureEvent)):
            evidence = session.action_evidence(event.tool_use_id) or {}
            outcome = session.tool_call_end(tool_call_end(event))
            observe.record(
                {
                    "event": "hook_outcome",
                    **evidence,
                    "outcome": outcome.value,
                    "outcome_source": event.hook_event_name,
                    "duration_ms": event.duration_ms,
                }
            )
            return None
        raise ValueError(f"unsupported operation for event: {operation}")

    return handle


def _spawn_session_service(event: SessionEvent, *, data_root: Path) -> ConnectionInfo:
    existing_path = _connection_path(data_root, event.session_id)
    if existing_path.exists():
        try:
            existing = ConnectionInfo.from_file(existing_path)
            if request_session(existing, operation="status", payload={}).get("ok") is True:
                return existing
        except (OSError, ValueError, KeyError):
            pass
        existing_path.unlink(missing_ok=True)

    bootstrap = _bootstrap_path(data_root, event.session_id)
    payload = {
        "event": _bootstrap_event_payload(event),
        "data_root": str(data_root),
        "token": secrets.token_hex(32),
    }
    descriptor = os.open(bootstrap, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    try:
        os.write(
            descriptor,
            json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8"),
        )
        os.fsync(descriptor)
    finally:
        os.close(descriptor)

    executable = Path(sys.argv[0]).resolve() if sys.argv and sys.argv[0] else None
    if executable is not None and executable.suffix == ".pyz":
        command = [sys.executable, str(executable), "--serve", str(bootstrap)]
    else:
        command = [
            sys.executable,
            "-m",
            "marginal.integrations.claude_code.service",
            "--serve",
            str(bootstrap),
        ]
    environment = {
        name: value
        for name in (
            "PATH",
            "LANG",
            "LC_ALL",
            "SYSTEMROOT",
            "PYTHONPATH",
            "MARGINAL_PRIVACY_PROFILE",
            *DATA_ROOT_VARIABLES,
        )
        if (value := os.environ.get(name)) is not None
    }
    subprocess.Popen(
        command,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        env=environment,
        close_fds=True,
        start_new_session=True,
    )
    deadline = time.monotonic() + _READY_TIMEOUT_SECONDS
    while time.monotonic() < deadline:
        if existing_path.exists():
            try:
                connection = ConnectionInfo.from_file(existing_path)
                if request_session(connection, operation="status", payload={}).get("ok") is True:
                    return connection
            except (OSError, ValueError, KeyError):
                pass
        time.sleep(0.05)
    bootstrap.unlink(missing_ok=True)
    raise RuntimeError("Claude Code session service did not become ready")


def selected_privacy_profile() -> PrivacyProfile:
    """Return the configured ledger privacy profile, defaulting to local-only.

    The ledger lives in the plugin's own data directory on the user's machine, so
    ``LOCAL_FULL`` is the default. Set ``MARGINAL_PRIVACY_PROFILE`` to
    ``safe_telemetry`` or ``aggregate_export`` when the ledger may cross a trust
    boundary. An unrecognized value falls back to the local-only default rather
    than failing a hook.
    """

    configured = os.environ.get("MARGINAL_PRIVACY_PROFILE", "")
    if not configured:
        return PrivacyProfile.LOCAL_FULL
    try:
        return PrivacyProfile(configured.strip().casefold())
    except ValueError:
        return PrivacyProfile.LOCAL_FULL


def _privacy_key_path(data_root: Path, profile: PrivacyProfile) -> Path | None:
    if profile is not PrivacyProfile.SAFE_TELEMETRY:
        return None
    return data_root / "privacy" / "pseudonym.key"


def _build_session(
    event: SessionEvent, *, data_root: Path
) -> tuple[ObserveSession, HookSessionRuntime]:
    profile = selected_privacy_profile()
    observe = build_observe_session(
        engine=ENGINE,
        session_id=event.session_id,
        workspace=event.cwd,
        data_root=data_root,
        privacy_profile=profile,
        privacy_key_path=_privacy_key_path(data_root, profile),
    )
    observe.record(
        {
            "event": "hook_session_start",
            "source": event.source,
            "capability_level": observe.runtime.capabilities.level,
            "privacy_profile_selected": selected_privacy_profile().value,
        }
    )
    return observe, HookSessionRuntime(observe.runtime, workspace=event.cwd)


def _serve_bootstrap(path: Path) -> int:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    finally:
        path.unlink(missing_ok=True)
    event = parse_hook_event(payload["event"])
    if not isinstance(event, SessionEvent) or event.hook_event_name != "SessionStart":
        return 2
    data_root = Path(payload["data_root"]).resolve()
    observe, session = _build_session(event, data_root=data_root)
    shutdown_event = threading.Event()
    server = SessionServer(
        data_root=data_root,
        session_id=event.session_id,
        token=str(payload["token"]),
        handler=_handler(session, observe=observe, shutdown_event=shutdown_event),
    )
    server.start()
    shutdown_event.wait()
    server.stop()
    return 0


def start_session_service(event: SessionEvent, *, data_root: str | Path) -> ConnectionInfo:
    """Start an in-process session service. Used by tests and embedding callers."""

    if event.hook_event_name != "SessionStart":
        raise ValueError("start_session_service requires SessionStart")
    root = Path(data_root).resolve()
    key = (root, event.session_id)
    active = _SERVERS.get(key)
    if active is not None:
        if request_session(active[0].connection, operation="status", payload={}).get("ok") is True:
            return active[0].connection
        _SERVERS.pop(key, None)
    observe, session = _build_session(event, data_root=root)
    server = SessionServer(
        data_root=root,
        session_id=event.session_id,
        token=secrets.token_hex(32),
        handler=_handler(session, observe=observe),
    )
    connection = server.start()
    _SERVERS[key] = (server, session)
    return connection


def stop_session_service(session_id: str, *, data_root: str | Path) -> None:
    """Close one session, whether it runs in this process or in a spawned service."""

    root = Path(data_root).resolve()
    key = (root, session_id)
    active = _SERVERS.pop(key, None)
    if active is not None:
        server, session = active
        try:
            request_session(server.connection, operation="close", payload={})
        finally:
            session.close()
            server.stop()
        return
    connection_path = _connection_path(root, session_id)
    if not connection_path.exists():
        return
    try:
        connection = ConnectionInfo.from_file(connection_path)
    except (OSError, ValueError, KeyError):
        connection_path.unlink(missing_ok=True)
        return
    request_session(connection, operation="close", payload={})


def run_hook(payload: dict[str, Any], *, data_root: str | Path) -> HookResult:
    """Execute one hook. Every integration fault fails open."""

    root = Path(data_root).resolve()
    event: ClaudeCodeHookEvent | None = None
    try:
        event = parse_hook_event(payload)
        if isinstance(event, SessionEvent):
            if event.hook_event_name == "SessionStart":
                _spawn_session_service(event, data_root=root)
            else:
                stop_session_service(event.session_id, data_root=root)
            return HookResult(exit_code=0)

        connection_path = _connection_path(root, event.session_id)
        if not connection_path.exists():
            return HookResult(exit_code=0, warning_code="SERVICE_UNAVAILABLE")
        connection = ConnectionInfo.from_file(connection_path)
        operation = "pre" if isinstance(event, PreToolUseEvent) else "post"
        response = request_session(connection, operation=operation, payload=payload)
        if response.get("ok") is not True:
            return HookResult(
                exit_code=0,
                warning_code=str(response.get("error_code", "SERVICE_ERROR")),
            )
        result = response.get("result")
        return HookResult(exit_code=0, output=result if isinstance(result, dict) else None)
    except Exception:
        return HookResult(exit_code=0, warning_code="INTEGRATION_ERROR")


def observe_outcome(payload: dict[str, Any]) -> ActionOutcomeStatus:
    """Classify one completion payload without touching session state."""

    event = parse_hook_event(payload)
    if not isinstance(event, (PostToolUseEvent, PostToolUseFailureEvent)):
        raise ValueError("payload must be a PostToolUse or PostToolUseFailure event")
    return tool_call_end(event).outcome


def hook_main(argv: list[str] | None = None) -> int:
    """Entry point used by the plugin hook shim and by ``python -m``."""

    selected = list(sys.argv[1:] if argv is None else argv)
    if len(selected) == 2 and selected[0] == "--serve":
        return _serve_bootstrap(Path(selected[1]).resolve())
    data_root = data_root_from_environment()
    if not data_root:
        return 0
    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, UnicodeDecodeError, OSError):
        return 0
    if not isinstance(payload, dict):
        return 0
    result = run_hook(payload, data_root=data_root)
    if result.output is not None:
        print(json.dumps(result.output, sort_keys=True, separators=(",", ":")))
    return result.exit_code


if __name__ == "__main__":
    raise SystemExit(hook_main())
