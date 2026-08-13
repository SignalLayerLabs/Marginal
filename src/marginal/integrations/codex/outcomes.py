"""Conservative outcome classification for documented structured tool results."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from typing import Any

from marginal.controls import ActionOutcomeStatus

from .events import PostToolUseEvent

_SUCCESS_TEXT = {"success", "succeeded", "passed"}
_FAILURE_TEXT = {"failure", "failed", "error"}


def _structured_signals(response: Mapping[str, Any]) -> set[ActionOutcomeStatus]:
    signals: set[ActionOutcomeStatus] = set()
    exit_code = response.get("exit_code")
    if isinstance(exit_code, int) and not isinstance(exit_code, bool):
        signals.add(ActionOutcomeStatus.SUCCESS if exit_code == 0 else ActionOutcomeStatus.FAILURE)
    success = response.get("success")
    if isinstance(success, bool):
        signals.add(ActionOutcomeStatus.SUCCESS if success else ActionOutcomeStatus.FAILURE)
    is_error = response.get("is_error")
    if isinstance(is_error, bool):
        signals.add(ActionOutcomeStatus.FAILURE if is_error else ActionOutcomeStatus.SUCCESS)
    for key in ("status", "outcome"):
        value = response.get(key)
        if not isinstance(value, str):
            continue
        normalized = value.strip().casefold()
        if normalized in _SUCCESS_TEXT:
            signals.add(ActionOutcomeStatus.SUCCESS)
        elif normalized in _FAILURE_TEXT:
            signals.add(ActionOutcomeStatus.FAILURE)
    return signals


def classify_tool_outcome(event: PostToolUseEvent) -> ActionOutcomeStatus:
    """Classify only explicit, mutually consistent structured outcome signals.

    Codex runs PostToolUse after non-zero shell exits. Human-readable response text is
    therefore evidence of completion, not evidence of success.
    """

    if not isinstance(event, PostToolUseEvent):
        raise TypeError("event must be a PostToolUseEvent")
    if not isinstance(event.tool_response, Mapping):
        return ActionOutcomeStatus.UNKNOWN
    signals = _structured_signals(event.tool_response)
    if len(signals) != 1:
        return ActionOutcomeStatus.UNKNOWN
    return next(iter(signals))


def completion_evidence_hash(response: Any) -> str:
    """Hash JSON-compatible completion evidence without retaining its contents."""

    try:
        canonical = json.dumps(
            response,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        )
    except (TypeError, ValueError):
        return ""
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
