"""Convert engine tool calls into privacy-safe protocol actions.

Normalization keeps raw arguments out of the action. Only a semantic hash of the
tool identity and its arguments is retained, so repetition can be detected without
persisting file paths, commands, or prompt material.
"""

from __future__ import annotations

import hashlib
import json
import re
from typing import Any

from marginal.models import Cost
from marginal.protocol import AgentAction, DeduplicationScope

from .events import ToolCallStart

_VERIFICATION_PATTERN = re.compile(
    r"(?:^|[\s/])(?:pytest|tox|nox|unittest|jest|vitest|mocha|rspec|"
    r"go\s+test|cargo\s+test|npm\s+(?:run\s+)?test|pnpm\s+(?:run\s+)?test|"
    r"yarn\s+test|ruff|mypy|pyright|eslint|tsc|git\s+diff\s+--check)(?:\s|$)",
    re.IGNORECASE,
)

_SHELL_TOOLS = frozenset({"bash", "shell", "exec", "exec_command", "terminal", "run"})
_EDIT_TOOLS = frozenset(
    {"apply_patch", "edit", "multiedit", "patch", "write", "write_file", "notebookedit"}
)
_READ_TOOLS = frozenset({"read", "read_file", "glob", "grep", "search", "list", "ls"})
_FETCH_TOOLS = frozenset({"webfetch", "websearch", "fetch", "webread"})

_COMMAND_KEYS = ("command", "cmd", "script")


def _canonical_json(value: Any) -> str:
    try:
        return json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        )
    except (TypeError, ValueError) as exc:
        raise ValueError("tool_input must have a canonical JSON representation") from exc


def semantic_key(start: ToolCallStart) -> str:
    """Hash the tool identity and arguments that define one semantic action."""

    canonical = _canonical_json(
        {"tool_name": start.tool_name.casefold(), "tool_input": dict(start.tool_input)}
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _command(start: ToolCallStart) -> str:
    for key in _COMMAND_KEYS:
        value = start.tool_input.get(key)
        if isinstance(value, str):
            return value
    return ""


def classify_action(start: ToolCallStart) -> tuple[str, bool]:
    """Return a generic action kind and whether the call reads as verification."""

    tool = start.tool_name.casefold()
    command = _command(start)
    if command and _VERIFICATION_PATTERN.search(command):
        return "verification", True
    if tool in _SHELL_TOOLS:
        return "shell", False
    if tool in _EDIT_TOOLS:
        return "edit", False
    if tool in _READ_TOOLS:
        return "read", False
    if tool in _FETCH_TOOLS:
        return "fetch", False
    if tool.startswith("mcp"):
        return "mcp", False
    return "tool", False


def normalize_tool_call(
    start: ToolCallStart,
    *,
    engine: str,
    state_hash: str,
    previous_evidence_hash: str = "",
) -> AgentAction:
    """Return a normalized action that retains no raw arguments.

    ``state_hash`` may be empty when the workspace is not observable. Empty state
    makes every repetition control fail open rather than invent certainty.
    """

    if not isinstance(start, ToolCallStart):
        raise TypeError("start must be a ToolCallStart")
    if not isinstance(engine, str) or not engine.strip():
        raise ValueError("engine must be a non-empty string")
    if not isinstance(state_hash, str):
        raise TypeError("state_hash must be a string")
    if not isinstance(previous_evidence_hash, str):
        raise TypeError("previous_evidence_hash must be a string")

    kind, is_verification = classify_action(start)
    metadata = {
        "session_id": start.session_id,
        "turn_id": start.turn_id,
        "tool_name": start.tool_name,
        "state_hash": state_hash,
        "evidence_hash": previous_evidence_hash,
        "semantic_key": semantic_key(start),
    }
    return AgentAction(
        action_id=start.call_id,
        name=f"{engine} {start.tool_name} action",
        kind=kind,
        estimated_cost=Cost(),
        is_verification=is_verification,
        state_hash=state_hash,
        phase=f"{engine}-tool-use",
        deduplication_scope=DeduplicationScope.ONCE_PER_STATE,
        metadata=metadata,
    )
