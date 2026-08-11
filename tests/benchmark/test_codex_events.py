from __future__ import annotations

import json
from pathlib import Path

import pytest
from benchmark.codex_adapter.codex_events import EventParseError, parse_codex_jsonl


def _write(path: Path, events: list[dict[str, object]]) -> None:
    path.write_text("".join(json.dumps(event) + "\n" for event in events), encoding="utf-8")


def test_parser_extracts_usage_actions_and_exact_repetitions(tmp_path: Path) -> None:
    path = tmp_path / "events.jsonl"
    command = {
        "id": "item-1",
        "type": "command_execution",
        "command": "pytest -q",
        "aggregated_output": "ok",
        "exit_code": 0,
        "status": "completed",
    }
    _write(
        path,
        [
            {"type": "thread.started", "thread_id": "thread-1"},
            {"type": "turn.started"},
            {"type": "item.completed", "item": command},
            {"type": "item.completed", "item": {**command, "id": "item-2"}},
            {
                "type": "item.completed",
                "item": {
                    "id": "item-3",
                    "type": "command_execution",
                    "command": "rg needle src",
                    "aggregated_output": "src/a.py",
                    "exit_code": 0,
                    "status": "completed",
                },
            },
            {
                "type": "item.completed",
                "item": {
                    "id": "item-4",
                    "type": "file_change",
                    "changes": [{"path": "src/a.py", "kind": "update"}],
                    "status": "completed",
                },
            },
            {
                "type": "item.completed",
                "item": {
                    "id": "item-5",
                    "type": "mcp_tool_call",
                    "server": "repo",
                    "tool": "lookup",
                    "arguments": {"q": "x"},
                    "result": {},
                    "error": None,
                    "status": "completed",
                },
            },
            {
                "type": "item.completed",
                "item": {
                    "id": "item-6",
                    "type": "web_search",
                    "query": "docs",
                    "action": {"type": "search"},
                },
            },
            {
                "type": "turn.completed",
                "usage": {
                    "input_tokens": 100,
                    "cached_input_tokens": 40,
                    "cache_write_input_tokens": 0,
                    "output_tokens": 25,
                    "reasoning_output_tokens": 10,
                },
            },
        ],
    )

    metrics = parse_codex_jsonl(path)

    assert metrics.thread_id == "thread-1"
    assert metrics.completed is True
    assert metrics.tokens == {
        "input": 100,
        "cached_input": 40,
        "output": 25,
        "reasoning": 10,
        "total": 125,
    }
    assert metrics.tool_calls == 6
    assert metrics.shell_commands == 3
    assert metrics.file_operations == 1
    assert metrics.searches == 2
    assert metrics.test_executions == 2
    assert metrics.repeated_calls == 1


def test_started_items_are_not_double_counted(tmp_path: Path) -> None:
    path = tmp_path / "events.jsonl"
    item = {
        "id": "item-1",
        "type": "command_execution",
        "command": "git status",
        "aggregated_output": "",
        "exit_code": None,
        "status": "in_progress",
    }
    _write(
        path,
        [
            {"type": "thread.started", "thread_id": "thread-1"},
            {"type": "turn.started"},
            {"type": "item.started", "item": item},
            {
                "type": "item.completed",
                "item": {**item, "exit_code": 0, "status": "completed"},
            },
            {
                "type": "turn.completed",
                "usage": {
                    "input_tokens": 1,
                    "cached_input_tokens": 0,
                    "output_tokens": 1,
                    "reasoning_output_tokens": 0,
                },
            },
        ],
    )

    assert parse_codex_jsonl(path).tool_calls == 1


def test_failed_turn_and_stream_error_are_retained(tmp_path: Path) -> None:
    path = tmp_path / "events.jsonl"
    _write(
        path,
        [
            {"type": "error", "message": "transport warning"},
            {"type": "turn.failed", "error": {"message": "model failed"}},
        ],
    )

    metrics = parse_codex_jsonl(path)
    assert metrics.completed is False
    assert metrics.tokens is None
    assert metrics.errors == ("transport warning", "model failed")


def test_malformed_or_negative_usage_is_rejected(tmp_path: Path) -> None:
    malformed = tmp_path / "malformed.jsonl"
    malformed.write_text("not json\n", encoding="utf-8")
    with pytest.raises(EventParseError, match="line 1"):
        parse_codex_jsonl(malformed)

    negative = tmp_path / "negative.jsonl"
    _write(
        negative,
        [
            {
                "type": "turn.completed",
                "usage": {
                    "input_tokens": -1,
                    "cached_input_tokens": 0,
                    "output_tokens": 0,
                    "reasoning_output_tokens": 0,
                },
            }
        ],
    )
    with pytest.raises(EventParseError, match="non-negative"):
        parse_codex_jsonl(negative)


@pytest.mark.parametrize(
    ("input_tokens", "cached_tokens", "output_tokens", "reasoning_tokens"),
    [(1, 2, 1, 0), (1, 0, 1, 2)],
)
def test_usage_subsets_and_completed_lifecycle_are_validated(
    tmp_path: Path,
    input_tokens: int,
    cached_tokens: int,
    output_tokens: int,
    reasoning_tokens: int,
) -> None:
    invalid = tmp_path / "invalid.jsonl"
    _write(
        invalid,
        [
            {"type": "thread.started", "thread_id": "thread-1"},
            {"type": "turn.started"},
            {
                "type": "turn.completed",
                "usage": {
                    "input_tokens": input_tokens,
                    "cached_input_tokens": cached_tokens,
                    "output_tokens": output_tokens,
                    "reasoning_output_tokens": reasoning_tokens,
                },
            },
        ],
    )
    with pytest.raises(EventParseError, match="subset"):
        parse_codex_jsonl(invalid)

    incomplete = tmp_path / "incomplete.jsonl"
    _write(
        incomplete,
        [
            {
                "type": "turn.completed",
                "usage": {
                    "input_tokens": 1,
                    "cached_input_tokens": 0,
                    "output_tokens": 1,
                    "reasoning_output_tokens": 0,
                },
            }
        ],
    )
    with pytest.raises(EventParseError, match="lifecycle"):
        parse_codex_jsonl(incomplete)
