"""Conservative outcome classification for structured tool results.

An engine that reports a structured result can prove success or failure. Anything
else is ``UNKNOWN``: human-readable output text is evidence of completion, never
evidence of success.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from typing import Any

from marginal.controls import ActionOutcomeStatus

_SUCCESS_TEXT = frozenset({"success", "succeeded", "passed", "completed"})
_FAILURE_TEXT = frozenset({"failure", "failed", "error", "errored"})
_EXIT_KEYS = ("exit_code", "exitCode", "exit", "returncode", "status_code")
_NESTED_KEYS = ("metadata", "result", "state")


def _exit_signal(response: Mapping[str, Any]) -> set[ActionOutcomeStatus]:
    signals: set[ActionOutcomeStatus] = set()
    for key in _EXIT_KEYS:
        value = response.get(key)
        if isinstance(value, bool) or not isinstance(value, int):
            continue
        signals.add(ActionOutcomeStatus.SUCCESS if value == 0 else ActionOutcomeStatus.FAILURE)
    return signals


def _boolean_signal(response: Mapping[str, Any]) -> set[ActionOutcomeStatus]:
    signals: set[ActionOutcomeStatus] = set()
    success = response.get("success")
    if isinstance(success, bool):
        signals.add(ActionOutcomeStatus.SUCCESS if success else ActionOutcomeStatus.FAILURE)
    for key in ("is_error", "isError", "error"):
        value = response.get(key)
        if isinstance(value, bool):
            signals.add(ActionOutcomeStatus.FAILURE if value else ActionOutcomeStatus.SUCCESS)
    return signals


def _text_signal(response: Mapping[str, Any]) -> set[ActionOutcomeStatus]:
    signals: set[ActionOutcomeStatus] = set()
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


def _signals(response: Mapping[str, Any], *, depth: int) -> set[ActionOutcomeStatus]:
    signals = _exit_signal(response) | _boolean_signal(response) | _text_signal(response)
    if depth <= 0:
        return signals
    for key in _NESTED_KEYS:
        nested = response.get(key)
        if isinstance(nested, Mapping):
            signals |= _signals(nested, depth=depth - 1)
    return signals


def classify_structured_result(result: Any) -> ActionOutcomeStatus:
    """Classify only explicit, mutually consistent structured outcome signals.

    Conflicting signals resolve to ``UNKNOWN`` because a governor must not pick a
    winner between two claims the engine itself did not reconcile.
    """

    if not isinstance(result, Mapping):
        return ActionOutcomeStatus.UNKNOWN
    signals = _signals(result, depth=2)
    if len(signals) != 1:
        return ActionOutcomeStatus.UNKNOWN
    return next(iter(signals))


def completion_evidence_hash(evidence: Any) -> str:
    """Hash JSON-compatible completion evidence without retaining its contents."""

    if evidence is None:
        return ""
    try:
        canonical = json.dumps(
            evidence,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        )
    except (TypeError, ValueError):
        return ""
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
