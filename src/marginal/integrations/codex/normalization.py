"""Convert raw Codex hook inputs into privacy-safe protocol actions."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

from marginal.models import Cost
from marginal.protocol import AgentAction, DeduplicationScope

from .events import PreToolUseEvent
from .intent import is_control_plane_action as _is_control_plane_action

_VERIFICATION_PATTERN = re.compile(
    r"(?:^|[\s/])(?:pytest|tox|nox|unittest|jest|vitest|mocha|rspec|"
    r"go\s+test|cargo\s+test|npm\s+(?:run\s+)?test|pnpm\s+(?:run\s+)?test|"
    r"yarn\s+test|ruff|mypy|pyright|eslint|tsc|git\s+diff\s+--check)(?:\s|$)",
    re.IGNORECASE,
)


def is_control_plane_action(event: PreToolUseEvent, plugin_root: Path) -> bool:
    """Expose strict trusted-control recognition beside action normalization."""

    return _is_control_plane_action(event, plugin_root)


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


def _semantic_key(event: PreToolUseEvent) -> str:
    canonical = _canonical_json(
        {"tool_name": event.tool_name.casefold(), "tool_input": event.tool_input}
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _command(event: PreToolUseEvent) -> str:
    command = event.tool_input.get("command")
    return command if isinstance(command, str) else ""


def _action_kind(event: PreToolUseEvent) -> tuple[str, bool]:
    tool = event.tool_name.casefold()
    command = _command(event)
    if command and _VERIFICATION_PATTERN.search(command):
        return "verification", True
    if tool in {"bash", "shell", "exec", "exec_command", "terminal"}:
        return "shell", False
    if tool in {"apply_patch", "edit", "write", "write_file"}:
        return "edit", False
    if tool.startswith("mcp"):
        return "mcp", False
    return "tool", False


def normalize_pre_tool_use(
    event: PreToolUseEvent,
    *,
    state_hash: str,
    previous_evidence_hash: str = "",
) -> AgentAction:
    """Return a normalized action without retaining raw arguments or descriptions."""

    if not isinstance(event, PreToolUseEvent):
        raise TypeError("event must be a PreToolUseEvent")
    if not isinstance(state_hash, str) or not state_hash.strip():
        raise ValueError("state_hash must be a non-empty string")
    if not isinstance(previous_evidence_hash, str):
        raise TypeError("previous_evidence_hash must be a string")

    semantic_key = _semantic_key(event)
    kind, is_verification = _action_kind(event)
    metadata = {
        "session_id": event.session_id,
        "turn_id": event.turn_id,
        "tool_name": event.tool_name,
        "state_hash": state_hash,
        "evidence_hash": previous_evidence_hash,
        "semantic_key": semantic_key,
    }
    return AgentAction(
        action_id=event.tool_use_id,
        name=f"Codex {event.tool_name} action",
        kind=kind,
        estimated_cost=Cost(),
        is_verification=is_verification,
        state_hash=state_hash,
        phase="codex-tool-use",
        deduplication_scope=DeduplicationScope.ONCE_PER_STATE,
        metadata=metadata,
    )
