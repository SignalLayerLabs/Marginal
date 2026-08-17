"""Engine-neutral session lifecycle for hook-based adapters.

The session runtime correlates a proposed tool call with its completion, settles
each accepted action exactly once, and records repetition evidence. It contains no
economic policy: every decision comes from the shared core through
``UniversalRuntime``.

This runtime observes. It never converts a stop recommendation into a denial. An
engine that can block still needs an evidence gate before enforcement, and no such
gate has been earned for the adapters built on this module.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

from marginal.controls import ActionOutcomeStatus, NoProgressDetector, NoProgressSignal
from marginal.models import Cost
from marginal.protocol import AgentAction, AgentDecision
from marginal.runtime import UniversalRuntime

from .events import ToolCallEnd, ToolCallStart
from .normalization import normalize_tool_call
from .outcomes import completion_evidence_hash
from .state import workspace_state_hash


class HookIntegrationError(RuntimeError):
    """Raised when hook lifecycle identity is missing or inconsistent."""


class HookSessionRuntime:
    """Correlate one engine session's tool calls over the provider-neutral runtime."""

    def __init__(
        self,
        runtime: UniversalRuntime,
        *,
        workspace: str | Path,
        detector: NoProgressDetector | None = None,
    ) -> None:
        if not isinstance(runtime, UniversalRuntime):
            raise TypeError("runtime must be a UniversalRuntime")
        self.runtime = runtime
        self.workspace = Path(workspace)
        self.detector = detector or NoProgressDetector()
        self._pending: dict[str, AgentAction] = {}
        self._evidence_by_semantic_key: dict[str, str] = {}
        self._last_signal: NoProgressSignal | None = None
        self._last_action_evidence: dict[str, str] | None = None
        self._successful = 0
        self._failed = 0
        self._unknown = 0
        self._unmatched = 0
        self._recommended_stops = 0
        self._closed = False

    @property
    def engine(self) -> str:
        return self.runtime.engine

    @property
    def last_no_progress_signal(self) -> NoProgressSignal | None:
        return self._last_signal

    @property
    def last_action_evidence(self) -> dict[str, str] | None:
        return dict(self._last_action_evidence) if self._last_action_evidence else None

    def tool_call_start(self, start: ToolCallStart) -> AgentDecision:
        """Authorize one proposed tool call and record its repetition evidence."""

        self._ensure_open()
        self._validate_session(start.session_id)
        if start.call_id in self._pending:
            raise HookIntegrationError(f"tool identity is already pending: {start.call_id}")

        state_hash = workspace_state_hash(self.workspace)
        action = normalize_tool_call(start, engine=self.engine, state_hash=state_hash)
        key = str(action.metadata["semantic_key"])
        evidence_hash = self._evidence_by_semantic_key.get(key, "")
        if evidence_hash:
            action = normalize_tool_call(
                start,
                engine=self.engine,
                state_hash=state_hash,
                previous_evidence_hash=evidence_hash,
            )
        self._last_action_evidence = self._safe_action_evidence(action)
        self._last_signal = self.detector.evaluate(key, state_hash, evidence_hash)
        if self._last_signal.should_recommend_stop:
            self._recommended_stops += 1

        decision = self.runtime.before_action(action)
        if decision.allowed:
            self._pending[start.call_id] = action
        return decision

    def tool_call_end(self, end: ToolCallEnd) -> ActionOutcomeStatus:
        """Settle one completed tool call using only the outcome its engine proved."""

        self._ensure_open()
        self._validate_session(end.session_id)
        action = self._pending.pop(end.call_id, None)
        if action is None:
            # A completion without a recorded proposal means hook coverage was
            # incomplete for this call. Report it instead of settling an action
            # the ledger never authorized.
            self._unmatched += 1
            return ActionOutcomeStatus.UNKNOWN
        if str(action.metadata.get("tool_name", "")) != end.tool_name:
            raise HookIntegrationError(
                f"completion tool identity does not match the proposal: {end.call_id}"
            )

        actual_cost = self._actual_cost(end)
        if end.outcome is ActionOutcomeStatus.SUCCESS:
            self.runtime.after_action(end.call_id, actual_cost=actual_cost)
            self._successful += 1
        elif end.outcome is ActionOutcomeStatus.FAILURE:
            self.runtime.fail_action(
                end.call_id,
                reason=f"{self.engine} reported an explicit tool failure",
                actual_cost=actual_cost,
            )
            self._failed += 1
        else:
            self.runtime.fail_action(
                end.call_id,
                reason=f"{self.engine} completion outcome was not observable",
                actual_cost=actual_cost,
            )
            self._unknown += 1

        key = str(action.metadata["semantic_key"])
        evidence_hash = completion_evidence_hash(end.evidence)
        self.detector.observe(
            key,
            workspace_state_hash(self.workspace),
            evidence_hash,
            end.outcome,
        )
        if evidence_hash:
            self._evidence_by_semantic_key[key] = evidence_hash
        return end.outcome

    def pending_action_ids(self) -> tuple[str, ...]:
        return tuple(sorted(self._pending))

    def action_evidence(self, action_id: str) -> dict[str, str] | None:
        action = self._pending.get(action_id)
        return self._safe_action_evidence(action) if action is not None else None

    def summary(self) -> dict[str, int]:
        return {
            "successful_observations": self._successful,
            "failed_observations": self._failed,
            "unknown_observations": self._unknown,
            "completed_observations": self._successful + self._failed + self._unknown,
            "unmatched_completions": self._unmatched,
            "recommended_stops": self._recommended_stops,
            "pending_actions": len(self._pending),
            "enforced_denials": 0,
        }

    def close(self) -> None:
        """Settle every proposal the engine never reported a completion for."""

        if self._closed:
            return
        for action_id in tuple(self._pending):
            self.runtime.fail_action(
                action_id,
                reason=f"{self.engine} session ended before the outcome was observable",
            )
            self._unknown += 1
            self._pending.pop(action_id)
        self._closed = True

    @staticmethod
    def _actual_cost(end: ToolCallEnd) -> Cost | None:
        """Return measured latency only. These hook surfaces expose no token usage."""

        if end.duration_ms is None:
            return None
        return Cost(latency_ms=int(end.duration_ms))

    @staticmethod
    def _safe_action_evidence(action: AgentAction) -> dict[str, str]:
        return {
            "action_hash": hashlib.sha256(action.action_id.encode("utf-8")).hexdigest(),
            "semantic_key": str(action.metadata.get("semantic_key", "")),
            "state_hash": action.state_hash,
            "evidence_hash": str(action.metadata.get("evidence_hash", "")),
        }

    def _ensure_open(self) -> None:
        if self._closed:
            raise HookIntegrationError(f"{self.engine} session runtime is closed")

    def _validate_session(self, session_id: str) -> None:
        if session_id != self.runtime.session_id:
            raise HookIntegrationError("hook session identity does not match runtime identity")
