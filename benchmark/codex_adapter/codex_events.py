"""Strict accounting over the stable ``codex exec --json`` event stream."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

_TEST_COMMAND = re.compile(
    r"(?:^|[;&|]\s*)(?:\S*/)?(?:pytest|py\.test|tox|nox|go\s+test|cargo\s+test|"
    r"npm\s+(?:run\s+)?test|pnpm\s+(?:run\s+)?test|yarn\s+(?:run\s+)?test|"
    r"python(?:\d+(?:\.\d+)?)?\s+-m\s+(?:pytest|unittest))\b",
    re.IGNORECASE,
)
_SEARCH_COMMAND = re.compile(
    r"(?:^|[;&|]\s*)(?:\S*/)?(?:rg|grep|find|fd)(?:\s|$)|"
    r"(?:^|[;&|]\s*)git\s+grep(?:\s|$)",
    re.IGNORECASE,
)


class EventParseError(ValueError):
    """Raised when raw Codex telemetry cannot support auditable metrics."""


@dataclass(frozen=True, slots=True)
class CodexMetrics:
    thread_id: str | None
    completed: bool
    tokens: dict[str, int] | None
    tool_calls: int
    shell_commands: int
    file_operations: int
    searches: int
    test_executions: int
    repeated_calls: int
    errors: tuple[str, ...]


def _canonical(value: object) -> str:
    try:
        return json.dumps(
            value,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        )
    except (TypeError, ValueError) as exc:
        raise EventParseError("event contains non-canonical JSON") from exc


def _usage(event: dict[str, Any]) -> dict[str, int]:
    usage = event.get("usage")
    if not isinstance(usage, dict):
        raise EventParseError("turn.completed is missing usage")
    fields = {
        "input": "input_tokens",
        "cached_input": "cached_input_tokens",
        "output": "output_tokens",
        "reasoning": "reasoning_output_tokens",
    }
    result: dict[str, int] = {}
    for output_name, input_name in fields.items():
        value = usage.get(input_name)
        if isinstance(value, bool) or not isinstance(value, int):
            raise EventParseError(f"{input_name} must be an integer")
        if value < 0:
            raise EventParseError("token usage must be non-negative")
        result[output_name] = value
    if result["cached_input"] > result["input"]:
        raise EventParseError("cached input must be a subset of input tokens")
    if result["reasoning"] > result["output"]:
        raise EventParseError("reasoning output must be a subset of output tokens")
    # Codex reports cached input as a subset of input and reasoning as a subset of output.
    result["total"] = result["input"] + result["output"]
    return result


def _identity(item: dict[str, Any]) -> str | None:
    item_type = item.get("type")
    if item_type == "command_execution":
        command = item.get("command")
        return f"command:{command}" if isinstance(command, str) else None
    if item_type == "file_change":
        return f"file_change:{_canonical(item.get('changes'))}"
    if item_type == "mcp_tool_call":
        return "mcp:" + _canonical(
            {
                "server": item.get("server"),
                "tool": item.get("tool"),
                "arguments": item.get("arguments"),
            }
        )
    if item_type == "web_search":
        return f"web_search:{item.get('query')}"
    if item_type == "collab_tool_call":
        return "collab:" + _canonical({"tool": item.get("tool"), "prompt": item.get("prompt")})
    return None


def parse_codex_jsonl(path: str | Path) -> CodexMetrics:
    """Parse one complete run without guessing missing telemetry."""

    event_path = Path(path)
    thread_id: str | None = None
    turn_started = False
    completed = False
    tokens: dict[str, int] | None = None
    tool_calls = 0
    shell_commands = 0
    file_operations = 0
    searches = 0
    test_executions = 0
    repeated_calls = 0
    identities: set[str] = set()
    errors: list[str] = []

    with event_path.open(encoding="utf-8") as stream:
        for line_number, raw in enumerate(stream, start=1):
            if not raw.strip():
                continue
            try:
                event = json.loads(raw)
            except json.JSONDecodeError as exc:
                raise EventParseError(f"invalid JSON on line {line_number}: {exc.msg}") from exc
            if not isinstance(event, dict):
                raise EventParseError(f"event on line {line_number} must be an object")
            event_type = event.get("type")
            if event_type == "thread.started":
                value = event.get("thread_id")
                if isinstance(value, str) and value:
                    thread_id = value
            elif event_type == "turn.started":
                turn_started = True
            elif event_type == "turn.completed":
                if tokens is not None:
                    raise EventParseError("multiple turn.completed events are unsupported")
                tokens = _usage(event)
                completed = True
            elif event_type == "turn.failed":
                error = event.get("error")
                message = error.get("message") if isinstance(error, dict) else None
                errors.append(str(message or "turn failed"))
            elif event_type == "error":
                errors.append(str(event.get("message") or "unknown stream error"))
            elif event_type != "item.completed":
                continue

            if event_type != "item.completed":
                continue
            item = event.get("item")
            if not isinstance(item, dict):
                raise EventParseError(f"item.completed on line {line_number} has no item object")
            identity = _identity(item)
            if identity is None:
                continue
            tool_calls += 1
            if identity in identities:
                repeated_calls += 1
            identities.add(identity)

            item_type = item.get("type")
            if item_type == "command_execution":
                shell_commands += 1
                command = item.get("command")
                if isinstance(command, str):
                    searches += int(bool(_SEARCH_COMMAND.search(command)))
                    test_executions += int(bool(_TEST_COMMAND.search(command)))
            elif item_type == "file_change":
                file_operations += 1
            elif item_type == "web_search":
                searches += 1

    if completed and (thread_id is None or not turn_started):
        raise EventParseError("completed turn has an invalid thread/turn lifecycle")

    return CodexMetrics(
        thread_id=thread_id,
        completed=completed,
        tokens=tokens,
        tool_calls=tool_calls,
        shell_commands=shell_commands,
        file_operations=file_operations,
        searches=searches,
        test_executions=test_executions,
        repeated_calls=repeated_calls,
        errors=tuple(errors),
    )
