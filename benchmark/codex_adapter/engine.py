"""Persistent MARGINAL governance state for one Codex benchmark task."""

from __future__ import annotations

import hashlib
import json
import threading
import time
from collections.abc import Callable, Mapping
from dataclasses import replace
from pathlib import Path
from typing import Any

from marginal.budget import BudgetLimits
from marginal.controls import DiminishingReturnDetector
from marginal.models import Cost
from marginal.policy import MarginalPolicy
from marginal.profiles import PolicyProfile, policy_config_for_profile
from marginal.trace import JsonlTraceSink
from marginal.treasury import Treasury

from .normalization import normalize_pre_tool_use
from .workspace import workspace_state_hash


class IntegrationError(RuntimeError):
    """Raised when hook lifecycle state is inconsistent or cannot be settled safely."""


StateHasher = Callable[[str | Path], str]


def _canonical_hash(value: object) -> str:
    try:
        encoded = json.dumps(
            value,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise IntegrationError("tool_response is not canonical JSON") from exc
    return hashlib.sha256(encoded).hexdigest()


def _required_text(payload: Mapping[str, Any], field: str) -> str:
    value = payload.get(field)
    if not isinstance(value, str):
        raise TypeError(f"{field} must be a string")
    if not value.strip():
        raise ValueError(f"{field} must not be empty")
    return value


class CodexGovernanceEngine:
    """Own one in-memory Treasury across every tool call in a Codex task."""

    def __init__(
        self,
        *,
        events_path: str | Path,
        state_hasher: StateHasher = workspace_state_hash,
    ) -> None:
        detector = DiminishingReturnDetector()
        policy = MarginalPolicy(
            policy_config_for_profile(PolicyProfile.BALANCED),
            name="profile:balanced",
            version="2.0.0",
            diminishing_detector=detector,
        )
        self._events = JsonlTraceSink(events_path)
        self._treasury = Treasury(
            BudgetLimits(),
            policy=policy,
            trace_sink=self._events,
            mode="enforce",
            name="codex-task",
        )
        self._state_hasher = state_hasher
        self._pending: dict[str, Any] = {}
        self._evidence_by_semantic_key: dict[str, str] = {}
        self._applied_denies = 0
        self._lock = threading.RLock()

    def pre_tool_use(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        """Authorize a proposed Codex tool call and reserve it when allowed."""

        if not isinstance(payload, Mapping):
            raise TypeError("payload must be a mapping")
        tool_use_id = _required_text(payload, "tool_use_id")
        cwd = _required_text(payload, "cwd")
        with self._lock:
            if tool_use_id in self._pending:
                raise IntegrationError(f"tool_use_id {tool_use_id!r} is already pending")

            started = time.perf_counter_ns()
            state_hash = self._state_hasher(cwd)
            proposal = normalize_pre_tool_use(payload, state_hash=state_hash)
            semantic_key = str(proposal.action.metadata["marginal_semantic_key"])
            previous_evidence = self._evidence_by_semantic_key.get(semantic_key, "")
            if previous_evidence:
                proposal = normalize_pre_tool_use(
                    payload,
                    state_hash=state_hash,
                    previous_evidence_hash=previous_evidence,
                )
            preparation_ms = (time.perf_counter_ns() - started) / 1_000_000
            self._treasury.record_governance_overhead(latency_ms=preparation_ms)

            diminishing = self._treasury.policy.diminishing_signal(proposal.action)
            decision = self._treasury.authorize(proposal.action)
            if decision.allowed:
                self._pending[tool_use_id] = proposal.action
            else:
                self._applied_denies += 1

            result = {
                "allowed": decision.allowed,
                "recommended": decision.recommended,
                "reason": decision.reason,
                "reason_code": decision.reason_code,
                "expected_gain": decision.expected_gain,
                "same_state_repeats": (
                    diminishing.same_state_repeats if diminishing is not None else 0
                ),
            }
            self._events.emit(
                {
                    "event": "codex_pre_tool_use",
                    "tool_use_id": tool_use_id,
                    "tool_name": payload.get("tool_name"),
                    **result,
                }
            )
            return result

    def post_tool_use(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        """Settle a previously authorized tool call with observed state and evidence."""

        if not isinstance(payload, Mapping):
            raise TypeError("payload must be a mapping")
        tool_use_id = _required_text(payload, "tool_use_id")
        cwd = _required_text(payload, "cwd")
        if "tool_response" not in payload:
            raise ValueError("tool_response is required")
        with self._lock:
            action = self._pending.get(tool_use_id)
            if action is None:
                raise IntegrationError(f"tool_use_id {tool_use_id!r} is not pending")

            started = time.perf_counter_ns()
            state_hash = self._state_hasher(cwd)
            post_proposal = normalize_pre_tool_use(payload, state_hash=state_hash)
            identity_fields = ("session_id", "turn_id", "tool_name", "cwd")
            identity_matches = all(
                post_proposal.action.metadata[field] == action.metadata[field]
                for field in identity_fields
            ) and (
                post_proposal.action.metadata["marginal_semantic_key"]
                == action.metadata["marginal_semantic_key"]
            )
            if not identity_matches:
                raise IntegrationError(f"PostToolUse identity does not match {tool_use_id!r}")
            evidence_hash = _canonical_hash(payload["tool_response"])
            metadata = dict(action.metadata)
            metadata.update({"state_hash": state_hash, "evidence_hash": evidence_hash})
            settled_action = replace(action, metadata=metadata)
            preparation_ms = (time.perf_counter_ns() - started) / 1_000_000
            self._treasury.record_governance_overhead(latency_ms=preparation_ms)

            successful = settled_action.kind not in {"shell", "verification"}
            if successful:
                self._treasury.commit(settled_action)
            else:
                self._treasury.settle_failure(
                    settled_action,
                    Cost(),
                    reason="Codex PostToolUse does not expose the shell exit status",
                )
            del self._pending[tool_use_id]
            semantic_key = str(settled_action.metadata["marginal_semantic_key"])
            if successful:
                self._evidence_by_semantic_key[semantic_key] = evidence_hash
            self._events.emit(
                {
                    "event": "codex_post_tool_use",
                    "tool_use_id": tool_use_id,
                    "tool_name": payload.get("tool_name"),
                    "state_hash": state_hash,
                    "evidence_hash": evidence_hash,
                    "successful": successful,
                }
            )
            return {"settled": True, "successful": successful}

    def summary(self) -> dict[str, Any]:
        with self._lock:
            summary = self._treasury.summary()
            governance = summary["governance"]
            assert isinstance(governance, dict)
            summary["pending"] = len(self._pending)
            summary["interventions"] = {
                "recommended_denies": self._applied_denies,
                "applied_denies": self._applied_denies,
                "reviewed": governance["reviewed_stops"],
                "false_stops": governance["false_stops"],
            }
            return summary
