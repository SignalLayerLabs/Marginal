#!/usr/bin/env python3
"""Thin Codex hook process that forwards stdin to the task-scoped daemon."""

from __future__ import annotations

import argparse
import json
import os
import socket
import sys
from collections.abc import Mapping
from pathlib import Path
from typing import Any, TextIO

_MAX_MESSAGE_BYTES = 16 * 1024 * 1024


def hook_output(operation: str, result: Mapping[str, Any]) -> dict[str, Any] | None:
    """Translate a daemon result to the official Codex command-hook output shape."""

    if operation == "post":
        if result.get("settled") is not True:
            raise RuntimeError("PostToolUse was not settled")
        return None
    if operation != "pre":
        raise ValueError(f"unsupported hook operation: {operation}")
    allowed = result.get("allowed")
    if not isinstance(allowed, bool):
        raise RuntimeError("daemon pre result is missing boolean allowed")
    if allowed:
        return None
    reason = result.get("reason")
    if not isinstance(reason, str) or not reason.strip():
        raise RuntimeError("daemon deny result is missing a reason")
    reason_code = result.get("reason_code")
    suffix = f" [{reason_code}]" if isinstance(reason_code, str) and reason_code else ""
    return {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": f"{reason}{suffix}",
        }
    }


def _request_daemon(
    socket_path: Path, operation: str, payload: Mapping[str, Any]
) -> Mapping[str, Any]:
    encoded = json.dumps(
        {"operation": operation, "payload": payload},
        ensure_ascii=False,
        allow_nan=False,
        separators=(",", ":"),
    ).encode("utf-8")
    if len(encoded) > _MAX_MESSAGE_BYTES:
        raise RuntimeError("hook request exceeds size limit")
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
        client.settimeout(60)
        client.connect(str(socket_path))
        client.sendall(encoded + b"\n")
        response = client.makefile("rb").readline(_MAX_MESSAGE_BYTES + 1)
    if not response:
        raise RuntimeError("daemon closed the connection without a response")
    if len(response) > _MAX_MESSAGE_BYTES:
        raise RuntimeError("daemon response exceeds size limit")
    decoded = json.loads(response)
    if not isinstance(decoded, Mapping):
        raise RuntimeError("daemon response must be a JSON object")
    if decoded.get("ok") is not True:
        code = decoded.get("error_code", "UNKNOWN")
        message = decoded.get("message", "daemon rejected request")
        raise RuntimeError(f"daemon {code}: {message}")
    result = decoded.get("result")
    if not isinstance(result, Mapping):
        raise RuntimeError("daemon response is missing an object result")
    return result


def run_hook(
    operation: str,
    *,
    stdin: TextIO,
    stdout: TextIO,
    stderr: TextIO,
    socket_path: Path,
    failure_log: Path | None = None,
) -> int:
    """Run one synchronous hook invocation with explicit integration failure output."""

    try:
        raw = stdin.read(_MAX_MESSAGE_BYTES + 1)
        if len(raw.encode("utf-8")) > _MAX_MESSAGE_BYTES:
            raise RuntimeError("hook stdin exceeds size limit")
        payload = json.loads(raw)
        if not isinstance(payload, Mapping):
            raise TypeError("hook stdin must be a JSON object")
        daemon_operation = {"pre": "pre_tool_use", "post": "post_tool_use"}[operation]
        result = _request_daemon(socket_path, daemon_operation, payload)
        output = hook_output(operation, result)
        if output is not None:
            stdout.write(json.dumps(output, sort_keys=True) + "\n")
        return 0
    except Exception as exc:
        message = f"MARGINAL integration failure: {type(exc).__name__}: {exc}"
        stderr.write(message + "\n")
        if failure_log is not None:
            failure_log.parent.mkdir(parents=True, exist_ok=True)
            with failure_log.open("a", encoding="utf-8") as stream:
                stream.write(message + "\n")
        return 1


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=("pre", "post"))
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    socket_value = os.environ.get("MARGINAL_SOCKET", "")
    if not socket_value:
        sys.stderr.write("MARGINAL integration failure: MARGINAL_SOCKET is not set\n")
        return 1
    failure_log_value = os.environ.get("MARGINAL_HOOK_FAILURE_LOG", "")
    return run_hook(
        args.operation,
        stdin=sys.stdin,
        stdout=sys.stdout,
        stderr=sys.stderr,
        socket_path=Path(socket_value),
        failure_log=Path(failure_log_value) if failure_log_value else None,
    )


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
