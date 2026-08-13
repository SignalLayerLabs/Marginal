"""Per-session Codex governance service and fail-open hook entry point."""

from __future__ import annotations

import hashlib
import json
import os
import secrets
import subprocess
import sys
import threading
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from marginal import BudgetLimits, Treasury
from marginal.protocol import AgentCapabilities
from marginal.runtime import UniversalRuntime

from .events import (
    PostToolUseEvent,
    PreToolUseEvent,
    SessionEvent,
    build_pre_tool_output,
    parse_hook_event,
)
from .runtime import CodexSessionRuntime
from .transport import ConnectionInfo, SessionServer, request_session

_SERVERS: dict[tuple[Path, str], tuple[SessionServer, CodexSessionRuntime]] = {}


@dataclass(frozen=True, slots=True)
class HookResult:
    exit_code: int
    output: dict[str, Any] | None = None
    warning_code: str = ""


def _connection_path(data_root: Path, session_id: str) -> Path:
    return data_root / "sessions" / f"{session_id}.json"


def _repository_hash(workspace: Path) -> str:
    return hashlib.sha256(str(workspace.resolve()).encode("utf-8")).hexdigest()


def _handler(
    runtime: CodexSessionRuntime,
    *,
    shutdown_event: threading.Event | None = None,
) -> Any:
    def handle(operation: str, payload: dict[str, Any]) -> dict[str, Any] | None:
        if operation == "status":
            return runtime.summary()
        event = parse_hook_event(payload)
        if operation == "pre" and isinstance(event, PreToolUseEvent):
            decision = runtime.pre_tool_use(event)
            return build_pre_tool_output(
                allowed=decision.allowed,
                reason=decision.reason,
                reason_code=decision.reason_code,
            )
        if operation == "post" and isinstance(event, PostToolUseEvent):
            runtime.post_tool_use(event)
            return None
        if operation == "close":
            runtime.close()
            if shutdown_event is not None:
                threading.Timer(0.05, shutdown_event.set).start()
            return runtime.summary()
        raise ValueError("unsupported service operation")

    return handle


def _bootstrap_path(data_root: Path, session_id: str) -> Path:
    bootstrap_root = data_root / "bootstrap"
    bootstrap_root.mkdir(parents=True, exist_ok=True, mode=0o700)
    if os.name == "posix":
        bootstrap_root.chmod(0o700)
    return bootstrap_root / f"{session_id}-{secrets.token_hex(8)}.json"


def _spawn_session_service(
    event: SessionEvent,
    *,
    data_root: Path,
) -> ConnectionInfo:
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
        "event": asdict(event),
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

    executable = Path(sys.argv[0]).resolve()
    if executable.suffix == ".pyz":
        command = [sys.executable, str(executable), "--serve", str(bootstrap)]
    else:
        command = [
            sys.executable,
            "-m",
            "marginal.integrations.codex.service",
            "--serve",
            str(bootstrap),
        ]
    environment = {
        name: value
        for name in ("PATH", "LANG", "LC_ALL", "SYSTEMROOT", "PYTHONPATH")
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
    deadline = time.monotonic() + 5.0
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
    raise RuntimeError("Codex session service did not become ready")


def _serve_bootstrap(path: Path) -> int:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    finally:
        path.unlink(missing_ok=True)
    event = parse_hook_event(payload["event"])
    if not isinstance(event, SessionEvent) or event.hook_event_name != "SessionStart":
        return 2
    data_root = Path(payload["data_root"]).resolve()
    token = str(payload["token"])
    treasury = Treasury(BudgetLimits(), mode="shadow")
    universal = UniversalRuntime(
        treasury,
        engine="codex",
        session_id=event.session_id,
        task_id=_repository_hash(Path(event.cwd)),
        capabilities=AgentCapabilities(block_actions=True),
    )
    runtime = CodexSessionRuntime(universal, workspace=event.cwd)
    shutdown_event = threading.Event()
    server = SessionServer(
        data_root=data_root,
        session_id=event.session_id,
        token=token,
        handler=_handler(runtime, shutdown_event=shutdown_event),
    )
    server.start()
    shutdown_event.wait()
    server.stop()
    return 0


def start_session_service(
    event: SessionEvent,
    *,
    data_root: str | Path,
) -> ConnectionInfo:
    if event.hook_event_name != "SessionStart":
        raise ValueError("start_session_service requires SessionStart")
    root = Path(data_root).resolve()
    key = (root, event.session_id)
    active = _SERVERS.get(key)
    if active is not None:
        response = request_session(active[0].connection, operation="status", payload={})
        if response.get("ok") is True:
            return active[0].connection
        active[0].stop()
        _SERVERS.pop(key, None)

    treasury = Treasury(BudgetLimits(), mode="shadow")
    universal = UniversalRuntime(
        treasury,
        engine="codex",
        session_id=event.session_id,
        task_id=_repository_hash(Path(event.cwd)),
        capabilities=AgentCapabilities(block_actions=True),
    )
    runtime = CodexSessionRuntime(universal, workspace=event.cwd)
    server = SessionServer(
        data_root=root,
        session_id=event.session_id,
        token=secrets.token_hex(32),
        handler=_handler(runtime),
    )
    connection = server.start()
    _SERVERS[key] = (server, runtime)
    return connection


def stop_session_service(session_id: str, *, data_root: str | Path) -> None:
    root = Path(data_root).resolve()
    key = (root, session_id)
    active = _SERVERS.pop(key, None)
    if active is not None:
        server, runtime = active
        runtime.close()
        server.stop()
        return
    path = _connection_path(root, session_id)
    if path.exists():
        try:
            connection = ConnectionInfo.from_file(path)
            request_session(connection, operation="close", payload={})
        finally:
            path.unlink(missing_ok=True)


def _mode_path(data_root: Path, repository_hash: str) -> Path:
    return data_root / "repositories" / f"{repository_hash}.json"


def demote_repository(
    data_root: str | Path,
    *,
    repository_hash: str,
    reason: str,
    mode: str = "shadow",
) -> None:
    root = Path(data_root).resolve()
    target = _mode_path(root, repository_hash)
    target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    payload = {"schema_version": 1, "mode": mode, "reason": reason}
    descriptor = os.open(target, os.O_CREAT | os.O_TRUNC | os.O_WRONLY, 0o600)
    try:
        os.write(
            descriptor,
            json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8"),
        )
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def read_mode(data_root: str | Path, *, repository_hash: str) -> dict[str, Any]:
    target = _mode_path(Path(data_root).resolve(), repository_hash)
    if not target.exists():
        return {"schema_version": 1, "mode": "shadow", "reason": "default"}
    payload = json.loads(target.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("repository mode must be a JSON object")
    return payload


def _demote_all_enforced(data_root: Path, reason: str) -> None:
    repository_root = data_root / "repositories"
    if not repository_root.exists():
        return
    for path in repository_root.glob("*.json"):
        payload = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(payload, dict) and payload.get("mode") == "enforce":
            demote_repository(
                data_root,
                repository_hash=path.stem,
                reason=reason,
                mode="shadow",
            )


def run_hook(payload: dict[str, Any], *, data_root: str | Path) -> HookResult:
    """Execute one hook. Integration faults always fail open and demote enforcement."""

    root = Path(data_root).resolve()
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
            _demote_all_enforced(root, "SERVICE_UNAVAILABLE")
            return HookResult(exit_code=0, warning_code="SERVICE_UNAVAILABLE")
        connection = ConnectionInfo.from_file(connection_path)
        operation = "pre" if isinstance(event, PreToolUseEvent) else "post"
        response = request_session(connection, operation=operation, payload=payload)
        if response.get("ok") is not True:
            code = str(response.get("error_code", "SERVICE_ERROR"))
            _demote_all_enforced(root, code)
            return HookResult(exit_code=0, warning_code=code)
        result = response.get("result")
        output = result if isinstance(result, dict) else None
        return HookResult(exit_code=0, output=output)
    except Exception:
        _demote_all_enforced(root, "INTEGRATION_ERROR")
        return HookResult(exit_code=0, warning_code="INTEGRATION_ERROR")


def hook_main(argv: list[str] | None = None) -> int:
    """Zipapp entry point used by the native plugin hook shim."""

    selected = list(sys.argv[1:] if argv is None else argv)
    if len(selected) == 2 and selected[0] == "--serve":
        return _serve_bootstrap(Path(selected[1]).resolve())
    data_root_value = os.environ.get("PLUGIN_DATA")
    if not data_root_value:
        return 0
    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return 0
    if not isinstance(payload, dict):
        return 0
    result = run_hook(payload, data_root=data_root_value)
    if result.output is not None:
        print(json.dumps(result.output, sort_keys=True, separators=(",", ":")))
    return result.exit_code


if __name__ == "__main__":
    raise SystemExit(hook_main())
