"""Transactional Codex session lifecycle over the provider-neutral runtime."""

from __future__ import annotations

import hashlib
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from marginal.controls import ActionOutcomeStatus, NoProgressDetector, NoProgressSignal
from marginal.models import Cost, Decision
from marginal.protocol import AgentAction, AgentDecision
from marginal.runtime import UniversalRuntime

from .events import PostToolUseEvent, PreToolUseEvent
from .normalization import normalize_pre_tool_use
from .outcomes import classify_tool_outcome, completion_evidence_hash
from .state import workspace_state_hash


class CodexIntegrationError(RuntimeError):
    """Raised when hook lifecycle identity is missing or inconsistent."""


@dataclass(frozen=True, slots=True)
class _PendingAction:
    event: PreToolUseEvent
    action: AgentAction


class CodexSessionRuntime:
    """Correlate Codex hook events and settle each accepted action exactly once."""

    def __init__(
        self,
        runtime: UniversalRuntime,
        *,
        workspace: str | Path,
        detector: NoProgressDetector | None = None,
        enforcement_enabled: Callable[[], bool] | None = None,
    ) -> None:
        if not isinstance(runtime, UniversalRuntime):
            raise TypeError("runtime must be a UniversalRuntime")
        self.runtime = runtime
        self.workspace = Path(workspace).resolve()
        workspace_state_hash(self.workspace)
        self.detector = detector or NoProgressDetector()
        self._enforcement_enabled = enforcement_enabled or (lambda: False)
        self._pending: dict[str, _PendingAction] = {}
        self._evidence_by_semantic_key: dict[str, str] = {}
        self._last_signal: NoProgressSignal | None = None
        self._last_action_evidence: dict[str, str] | None = None
        self._successful = 0
        self._failed = 0
        self._unknown = 0
        self._enforced_denials = 0
        self._closed = False

    @property
    def last_no_progress_signal(self) -> NoProgressSignal | None:
        return self._last_signal

    @property
    def last_action_evidence(self) -> dict[str, str] | None:
        return dict(self._last_action_evidence) if self._last_action_evidence else None

    def pre_tool_use(self, event: PreToolUseEvent) -> AgentDecision:
        self._ensure_open()
        self._validate_session(event.session_id)
        if event.tool_use_id in self._pending:
            raise CodexIntegrationError(f"tool identity is already pending: {event.tool_use_id}")
        state_hash = workspace_state_hash(self.workspace)
        action = normalize_pre_tool_use(event, state_hash=state_hash)
        semantic_key = str(action.metadata["semantic_key"])
        evidence_hash = self._evidence_by_semantic_key.get(semantic_key, "")
        if evidence_hash:
            action = normalize_pre_tool_use(
                event,
                state_hash=state_hash,
                previous_evidence_hash=evidence_hash,
            )
        self._last_action_evidence = self._safe_action_evidence(action)
        self._last_signal = self.detector.evaluate(
            semantic_key,
            state_hash,
            evidence_hash,
        )
        if self._last_signal.enforcement_eligible and self._is_enforcement_enabled():
            self._enforced_denials += 1
            return AgentDecision.from_core(
                event.tool_use_id,
                Decision(
                    allowed=False,
                    reason="Repeated proven-success action produced no new state or evidence",
                    recommended=False,
                    recommendation_reason=(
                        "Repeated proven-success action produced no new state or evidence"
                    ),
                    reason_code="NO_PROGRESS_ENFORCED",
                    recommendation_reason_code="NO_PROGRESS_ENFORCED",
                    mode="enforce",
                    confidence=1.0,
                ),
            )
        decision = self.runtime.before_action(action)
        if decision.allowed:
            self._pending[event.tool_use_id] = _PendingAction(event=event, action=action)
        return decision

    def post_tool_use(self, event: PostToolUseEvent) -> ActionOutcomeStatus:
        self._ensure_open()
        self._validate_session(event.session_id)
        pending = self._pending.get(event.tool_use_id)
        if pending is None:
            raise CodexIntegrationError(
                f"PostToolUse identity does not match a pending action: {event.tool_use_id}"
            )
        self._validate_post_identity(pending.event, event)

        outcome = classify_tool_outcome(event)
        evidence_hash = completion_evidence_hash(event.tool_response)
        semantic_key = str(pending.action.metadata["semantic_key"])
        post_state_hash = workspace_state_hash(self.workspace)

        if outcome is ActionOutcomeStatus.SUCCESS:
            self.runtime.after_action(event.tool_use_id, actual_cost=Cost())
            self._successful += 1
        elif outcome is ActionOutcomeStatus.FAILURE:
            self.runtime.fail_action(
                event.tool_use_id,
                reason="Codex returned an explicit structured failure",
                actual_cost=Cost(),
            )
            self._failed += 1
        else:
            self.runtime.fail_action(
                event.tool_use_id,
                reason="Codex completion outcome was not observable",
            )
            self._unknown += 1

        self._pending.pop(event.tool_use_id)
        self.detector.observe(semantic_key, post_state_hash, evidence_hash, outcome)
        if evidence_hash:
            self._evidence_by_semantic_key[semantic_key] = evidence_hash
        return outcome

    def pending_action_ids(self) -> tuple[str, ...]:
        return tuple(sorted(self._pending))

    def action_evidence(self, action_id: str) -> dict[str, str] | None:
        pending = self._pending.get(action_id)
        return self._safe_action_evidence(pending.action) if pending is not None else None

    def summary(self) -> dict[str, int]:
        return {
            "successful_observations": self._successful,
            "failed_observations": self._failed,
            "unknown_observations": self._unknown,
            "completed_observations": self._successful + self._failed + self._unknown,
            "pending_actions": len(self._pending),
            "enforced_denials": self._enforced_denials,
        }

    def close(self) -> None:
        if self._closed:
            return
        for action_id in tuple(self._pending):
            self.runtime.fail_action(
                action_id,
                reason="Codex session ended before the action outcome was observable",
            )
            self._unknown += 1
            self._pending.pop(action_id)
        self._closed = True

    def _ensure_open(self) -> None:
        if self._closed:
            raise CodexIntegrationError("Codex session runtime is closed")

    def _is_enforcement_enabled(self) -> bool:
        try:
            enabled = self._enforcement_enabled()
        except Exception:
            return False
        return enabled if isinstance(enabled, bool) else False

    @staticmethod
    def _safe_action_evidence(action: AgentAction) -> dict[str, str]:
        return {
            "action_hash": hashlib.sha256(action.action_id.encode("utf-8")).hexdigest(),
            "semantic_key": str(action.metadata.get("semantic_key", "")),
            "state_hash": action.state_hash,
            "evidence_hash": str(action.metadata.get("evidence_hash", "")),
        }

    def _validate_session(self, session_id: str) -> None:
        if session_id != self.runtime.session_id:
            raise CodexIntegrationError("hook session identity does not match runtime identity")

    @staticmethod
    def _validate_post_identity(
        before: PreToolUseEvent,
        after: PostToolUseEvent,
    ) -> None:
        expected: tuple[Any, ...] = (
            before.session_id,
            before.turn_id,
            before.tool_name,
            before.tool_use_id,
            dict(before.tool_input),
        )
        observed: tuple[Any, ...] = (
            after.session_id,
            after.turn_id,
            after.tool_name,
            after.tool_use_id,
            dict(after.tool_input),
        )
        if expected != observed:
            raise CodexIntegrationError("PreToolUse and PostToolUse identity does not match")
