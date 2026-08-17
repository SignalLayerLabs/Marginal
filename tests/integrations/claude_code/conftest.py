"""Shared fixtures for the Claude Code integration tests.

The payload shapes mirror Claude Code 2.1.233. Every identifier, path, and value is
synthetic.
"""

import subprocess
from pathlib import Path
from typing import Any

import pytest

SESSION_ID = "synthetic-session-0001"
PROMPT_ID = "synthetic-prompt-0001"


def _git(repo: Path, *args: str) -> None:
    subprocess.run(
        ["git", *args],
        cwd=repo,
        check=True,
        capture_output=True,
        env={
            "PATH": "/usr/bin:/bin:/usr/local/bin",
            "HOME": str(repo),
            "GIT_AUTHOR_NAME": "Test",
            "GIT_AUTHOR_EMAIL": "test@example.invalid",
            "GIT_COMMITTER_NAME": "Test",
            "GIT_COMMITTER_EMAIL": "test@example.invalid",
        },
    )


@pytest.fixture
def workspace(tmp_path: Path) -> Path:
    """A committed Git work tree standing in for a Claude Code session directory."""

    directory = tmp_path / "workspace"
    directory.mkdir()
    _git(directory, "init", "-q")
    (directory / "example.txt").write_text("hello\n", encoding="utf-8")
    _git(directory, "add", "example.txt")
    _git(directory, "commit", "-qm", "initial")
    return directory


@pytest.fixture
def payloads(workspace: Path) -> "PayloadFactory":
    return PayloadFactory(workspace)


class PayloadFactory:
    """Build hook payloads in the shape Claude Code sends them."""

    def __init__(self, workspace: Path) -> None:
        self.workspace = workspace

    def _common(self) -> dict[str, Any]:
        return {
            "session_id": SESSION_ID,
            "cwd": str(self.workspace),
            "transcript_path": str(self.workspace / "transcript.jsonl"),
        }

    def session_start(self) -> dict[str, Any]:
        return {**self._common(), "hook_event_name": "SessionStart", "source": "startup"}

    def session_end(self) -> dict[str, Any]:
        return {
            **self._common(),
            "hook_event_name": "SessionEnd",
            "prompt_id": PROMPT_ID,
            "reason": "clear",
        }

    def pre_tool_use(
        self,
        call_id: str = "toolu_synthetic0001",
        *,
        tool_name: str = "Read",
        tool_input: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return {
            **self._common(),
            "hook_event_name": "PreToolUse",
            "permission_mode": "default",
            "prompt_id": PROMPT_ID,
            "tool_name": tool_name,
            "tool_use_id": call_id,
            "tool_input": tool_input or {"file_path": str(self.workspace / "example.txt")},
        }

    def post_tool_use(
        self,
        call_id: str = "toolu_synthetic0001",
        *,
        tool_name: str = "Read",
        tool_input: dict[str, Any] | None = None,
        tool_response: Any = None,
        duration_ms: float | None = 11.0,
    ) -> dict[str, Any]:
        if tool_response is None:
            tool_response = {
                "type": "text",
                "file": {
                    "filePath": str(self.workspace / "example.txt"),
                    "content": "hello\n",
                    "numLines": 1,
                    "startLine": 1,
                    "totalLines": 1,
                },
            }
        payload = {
            **self._common(),
            "hook_event_name": "PostToolUse",
            "permission_mode": "default",
            "prompt_id": PROMPT_ID,
            "tool_name": tool_name,
            "tool_use_id": call_id,
            "tool_input": tool_input or {"file_path": str(self.workspace / "example.txt")},
            "tool_response": tool_response,
        }
        if duration_ms is not None:
            payload["duration_ms"] = duration_ms
        return payload

    def post_tool_use_failure(
        self,
        call_id: str = "toolu_synthetic0002",
        *,
        tool_name: str = "Bash",
        tool_input: dict[str, Any] | None = None,
        error: str = "Exit code 3",
        is_interrupt: bool = False,
        duration_ms: float | None = 4.0,
    ) -> dict[str, Any]:
        return {
            **self._common(),
            "hook_event_name": "PostToolUseFailure",
            "permission_mode": "default",
            "prompt_id": PROMPT_ID,
            "tool_name": tool_name,
            "tool_use_id": call_id,
            "tool_input": tool_input or {"command": "exit 3", "description": "Run exit 3"},
            "error": error,
            "is_interrupt": is_interrupt,
            "duration_ms": duration_ms,
        }
