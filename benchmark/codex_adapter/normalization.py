"""Normalize Codex hook payloads into provider-neutral MARGINAL actions."""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from marginal.models import Action, Cost

_VERIFICATION_COMMAND = re.compile(
    r"(?:^|[;&|]\s*)(?:\S*/)?(?:pytest|py\.test|tox|nox|go\s+test|cargo\s+test|"
    r"npm\s+(?:run\s+)?test|pnpm\s+(?:run\s+)?test|yarn\s+(?:run\s+)?test|"
    r"python(?:\d+(?:\.\d+)?)?\s+-m\s+(?:pytest|unittest))\b",
    re.IGNORECASE,
)


@dataclass(frozen=True, slots=True)
class NormalizedProposal:
    """Validated hook identity paired with the action MARGINAL evaluates."""

    tool_use_id: str
    action: Action


def _required_text(payload: Mapping[str, Any], field: str) -> str:
    value = payload.get(field)
    if not isinstance(value, str):
        raise TypeError(f"{field} must be a string")
    if not value.strip():
        raise ValueError(f"{field} must not be empty")
    return value


def _canonical_json(value: Mapping[str, Any]) -> str:
    try:
        return json.dumps(
            value,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        )
    except (TypeError, ValueError) as exc:
        raise ValueError("tool_input must contain canonical JSON values") from exc


def _classify(tool_name: str, tool_input: Mapping[str, Any]) -> tuple[str, bool]:
    normalized = tool_name.strip().lower()
    if normalized in {"bash", "shell", "shell_command", "exec_command"}:
        command = tool_input.get("command", tool_input.get("cmd", ""))
        if isinstance(command, str) and _VERIFICATION_COMMAND.search(command):
            return "verification", True
        return "shell", False
    if normalized in {"apply_patch", "patch"}:
        return "edit", False
    if normalized.startswith("mcp__"):
        return "mcp", False
    return "tool", False


def _action_name(tool_name: str, tool_input: Mapping[str, Any]) -> str:
    candidate = tool_input.get("command", tool_input.get("cmd", tool_input.get("path", "")))
    if not isinstance(candidate, str) or not candidate.strip():
        return tool_name
    compact = " ".join(candidate.split())
    return f"{tool_name}: {compact[:160]}"


def normalize_pre_tool_use(
    payload: Mapping[str, Any],
    *,
    state_hash: str,
    previous_evidence_hash: str = "",
) -> NormalizedProposal:
    """Validate one ``PreToolUse`` payload and build its MARGINAL action.

    Hook payloads do not expose a defensible forecast of future token or dollar cost, so
    the benchmark deliberately reserves zero pre-execution cost. The resulting experiment
    isolates state-aware repetition control rather than claiming economic ROI calibration.
    """

    if not isinstance(payload, Mapping):
        raise TypeError("hook payload must be a mapping")
    session_id = _required_text(payload, "session_id")
    turn_id = _required_text(payload, "turn_id")
    tool_use_id = _required_text(payload, "tool_use_id")
    tool_name = _required_text(payload, "tool_name")
    cwd = _required_text(payload, "cwd")
    tool_input = payload.get("tool_input")
    if not isinstance(tool_input, Mapping):
        raise TypeError("tool_input must be a mapping")
    if not isinstance(state_hash, str) or not state_hash.strip():
        raise ValueError("state_hash must not be empty")
    if not isinstance(previous_evidence_hash, str):
        raise TypeError("previous_evidence_hash must be a string")

    canonical_input = _canonical_json(tool_input)
    semantic_material = f"{tool_name.strip().lower()}\0{canonical_input}".encode()
    semantic_key = hashlib.sha256(semantic_material).hexdigest()
    kind, is_verification = _classify(tool_name, tool_input)
    action = Action(
        name=_action_name(tool_name, tool_input),
        kind=kind,
        cost=Cost(),
        expected_gain=None,
        is_verification=is_verification,
        fingerprint=f"codex:{tool_use_id}",
        metadata={
            "phase": "codex-tool-use",
            "session_id": session_id,
            "turn_id": turn_id,
            "tool_use_id": tool_use_id,
            "tool_name": tool_name,
            "cwd": cwd,
            "state_hash": state_hash,
            "evidence_hash": previous_evidence_hash,
            "marginal_semantic_key": semantic_key,
        },
    )
    return NormalizedProposal(tool_use_id=tool_use_id, action=action)
