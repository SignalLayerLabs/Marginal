"""Newline-delimited JSON bridge between the OpenCode plugin and MARGINAL.

The OpenCode plugin lives in a long-running process, so it owns one bridge child
process instead of paying interpreter startup per tool call. The bridge reads one
request per line from stdin and writes one response per line to stdout.

Requests are only ever accepted from the process that spawned the bridge, over its
own pipes. There is no socket, no port, and no token, because there is no other
possible caller.

The bridge governs several sessions at once: a single OpenCode process can host more
than one, and tool calls from different sessions interleave.
"""

from __future__ import annotations

import json
import sys
import time
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any, TextIO

from marginal.privacy import PrivacyProfile

from ..hookkit.bootstrap import ObserveSession, build_observe_session
from ..hookkit.session import HookSessionRuntime
from .events import (
    OPERATIONS,
    SessionRequest,
    ToolEndRequest,
    ToolStartRequest,
    parse_request,
)
from .normalization import ENGINE, tool_call_end, tool_call_start
from .targets import OPENCODE, OpenCodeTarget, resolve_target

MAX_LINE_BYTES = 256 * 1024


@dataclass(slots=True)
class _Session:
    observe: ObserveSession
    runtime: HookSessionRuntime


def _error(code: str) -> dict[str, Any]:
    return {"ok": False, "error_code": code}


def _privacy_profile(configured: str) -> PrivacyProfile:
    if not configured:
        return PrivacyProfile.LOCAL_FULL
    try:
        return PrivacyProfile(configured.strip().casefold())
    except ValueError:
        return PrivacyProfile.LOCAL_FULL


class BridgeService:
    """Own every governed OpenCode session inside one bridge process."""

    def __init__(
        self,
        *,
        target: OpenCodeTarget = OPENCODE,
        data_root: str | Path | None = None,
        privacy_profile: PrivacyProfile | str = PrivacyProfile.LOCAL_FULL,
    ) -> None:
        self.target = target
        self.data_root = Path(data_root) if data_root is not None else target.data_root()
        self.privacy_profile = PrivacyProfile(privacy_profile)
        self._sessions: dict[str, _Session] = {}

    @property
    def session_ids(self) -> tuple[str, ...]:
        return tuple(sorted(self._sessions))

    def handle(self, operation: str, payload: Mapping[str, Any]) -> Mapping[str, Any] | None:
        """Dispatch one request. Unknown operations raise rather than pass silently."""

        if operation not in OPERATIONS:
            raise ValueError(f"unsupported bridge operation: {operation}")
        if operation == "status":
            return {
                "engine": self.target.engine,
                "sessions": len(self._sessions),
                "capability_level": "observe",
            }
        request = parse_request(operation, payload)
        if operation == "session_start" and isinstance(request, SessionRequest):
            self._open(request.session_id, request.workspace)
            return {"sessions": len(self._sessions)}
        if operation == "session_end" and isinstance(request, SessionRequest):
            return self._close(request.session_id)
        if operation == "tool_start" and isinstance(request, ToolStartRequest):
            return self._tool_start(request)
        if isinstance(request, ToolEndRequest):
            return self._tool_end(request)
        raise ValueError(f"payload does not match operation: {operation}")

    def close_all(self) -> None:
        for session_id in tuple(self._sessions):
            self._close(session_id)

    def _open(self, session_id: str, workspace: str) -> _Session:
        existing = self._sessions.get(session_id)
        if existing is not None:
            return existing
        observe = build_observe_session(
            engine=self.target.engine,
            session_id=session_id,
            workspace=workspace,
            data_root=self.data_root,
            privacy_profile=self.privacy_profile,
            privacy_key_path=(
                self.data_root / "privacy" / "pseudonym.key"
                if self.privacy_profile is PrivacyProfile.SAFE_TELEMETRY
                else None
            ),
        )
        observe.record(
            {
                "event": "hook_session_start",
                "capability_level": observe.runtime.capabilities.level,
                "privacy_profile_selected": self.privacy_profile.value,
            }
        )
        session = _Session(
            observe=observe,
            runtime=HookSessionRuntime(observe.runtime, workspace=workspace),
        )
        self._sessions[session_id] = session
        return session

    def _close(self, session_id: str) -> dict[str, Any]:
        session = self._sessions.pop(session_id, None)
        if session is None:
            return {"closed": False}
        session.runtime.close()
        summary = session.runtime.summary()
        session.observe.record(
            {
                "event": "hook_session_end",
                **{f"summary_{name}": value for name, value in summary.items()},
            }
        )
        return {"closed": True, **summary}

    def _tool_start(self, request: ToolStartRequest) -> dict[str, Any]:
        session = self._sessions.get(request.session_id)
        if session is None:
            # OpenCode has no guaranteed session-start hook, so the first observed
            # tool call opens the session.
            session = self._open(request.session_id, request.workspace or str(Path.cwd()))
        started = time.perf_counter_ns()
        decision = session.runtime.tool_call_start(tool_call_start(request))
        latency_ms = (time.perf_counter_ns() - started) / 1_000_000
        signal = session.runtime.last_no_progress_signal
        session.observe.record(
            {
                "event": "hook_decision",
                **(session.runtime.last_action_evidence or {}),
                "reason_code": decision.reason_code,
                "recommended": decision.recommended,
                "recommended_stop": bool(signal and signal.should_recommend_stop),
                "no_progress_reason_code": signal.reason_code if signal else "",
                "governance_latency_ms": latency_ms,
                "enforced": False,
            }
        )
        # Shadow Mode never asks OpenCode to change what it does next.
        return {"allow": True}

    def _tool_end(self, request: ToolEndRequest) -> dict[str, Any]:
        session = self._sessions.get(request.session_id)
        if session is None:
            return {"observed": False}
        evidence = session.runtime.action_evidence(request.call_id) or {}
        outcome = session.runtime.tool_call_end(tool_call_end(request))
        session.observe.record(
            {
                "event": "hook_outcome",
                **evidence,
                "outcome": outcome.value,
                "outcome_source": "tool.execute.after",
                "duration_ms": request.duration_ms,
            }
        )
        return {"observed": True, "outcome": outcome.value}


def _respond(stream: TextIO, payload: Mapping[str, Any]) -> None:
    stream.write(json.dumps(dict(payload), sort_keys=True, separators=(",", ":")) + "\n")
    stream.flush()


def serve(
    service: BridgeService,
    *,
    source: TextIO,
    destination: TextIO,
) -> int:
    """Serve requests until stdin closes. A bad request never stops the bridge."""

    for raw in source:
        if len(raw.encode("utf-8", errors="replace")) > MAX_LINE_BYTES:
            _respond(destination, _error("MESSAGE_TOO_LARGE"))
            continue
        line = raw.strip()
        if not line:
            continue
        try:
            request = json.loads(line)
        except (json.JSONDecodeError, UnicodeDecodeError):
            _respond(destination, _error("INVALID_MESSAGE"))
            continue
        if not isinstance(request, dict):
            _respond(destination, _error("INVALID_MESSAGE"))
            continue
        operation = request.get("operation")
        payload = request.get("payload", {})
        if not isinstance(operation, str) or not isinstance(payload, dict):
            _respond(destination, _error("INVALID_MESSAGE"))
            continue
        try:
            result = service.handle(operation, payload)
        except Exception:
            _respond(destination, _error("SERVICE_ERROR"))
            continue
        _respond(destination, {"ok": True, "result": result})
    service.close_all()
    return 0


def main(argv: list[str] | None = None) -> int:
    """Entry point the OpenCode plugin spawns."""

    import argparse
    import os

    parser = argparse.ArgumentParser(prog=f"python -m marginal.integrations.{ENGINE}.bridge")
    parser.add_argument("--target", default=OPENCODE.name)
    parser.add_argument("--data-root")
    arguments = parser.parse_args(argv)
    try:
        target = resolve_target(arguments.target)
    except ValueError:
        return 2
    service = BridgeService(
        target=target,
        data_root=arguments.data_root,
        privacy_profile=_privacy_profile(os.environ.get("MARGINAL_PRIVACY_PROFILE", "")),
    )
    return serve(service, source=sys.stdin, destination=sys.stdout)


if __name__ == "__main__":
    raise SystemExit(main())
