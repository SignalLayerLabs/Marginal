"""Shared fixtures for the OpenCode integration tests.

Payload shapes mirror OpenCode 1.18.18. Every identifier and value is synthetic.
"""

import subprocess
from pathlib import Path
from typing import Any

import pytest

SESSION_ID = "ses_synthetic0001"


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
    directory = tmp_path / "workspace"
    directory.mkdir()
    _git(directory, "init", "-q")
    (directory / "example.txt").write_text("hello\n", encoding="utf-8")
    _git(directory, "add", "example.txt")
    _git(directory, "commit", "-qm", "initial")
    return directory


@pytest.fixture
def requests(workspace: Path) -> "RequestFactory":
    return RequestFactory(workspace)


class RequestFactory:
    """Build bridge requests in the shape the plugin sends them."""

    def __init__(self, workspace: Path) -> None:
        self.workspace = workspace

    def session(self) -> dict[str, Any]:
        return {"session_id": SESSION_ID, "workspace": str(self.workspace)}

    def tool_start(
        self,
        call_id: str = "call_synthetic0001",
        *,
        tool_name: str = "read",
        arguments: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return {
            "session_id": SESSION_ID,
            "call_id": call_id,
            "tool_name": tool_name,
            "arguments": arguments or {"filePath": "./example.txt"},
            "workspace": str(self.workspace),
        }

    def tool_end(
        self,
        call_id: str = "call_synthetic0001",
        *,
        tool_name: str = "read",
        arguments: dict[str, Any] | None = None,
        evidence_digest: str = "a" * 64,
        signals: dict[str, Any] | None = None,
        duration_ms: float | None = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "session_id": SESSION_ID,
            "call_id": call_id,
            "tool_name": tool_name,
            "arguments": arguments or {"filePath": "./example.txt"},
            "evidence_digest": evidence_digest,
            "signals": signals if signals is not None else {},
        }
        if duration_ms is not None:
            payload["duration_ms"] = duration_ms
        return payload
