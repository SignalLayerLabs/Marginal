"""Local engine-neutral runtime for thin MARGINAL adapters."""

from __future__ import annotations

from dataclasses import replace

from .models import Action, Cost
from .outcomes import Outcome
from .protocol import AgentAction, AgentCapabilities, AgentDecision
from .treasury import Treasury


class UniversalRuntime:
    """Translate normalized agent actions into transactional MARGINAL operations."""

    def __init__(
        self,
        treasury: Treasury,
        *,
        engine: str,
        session_id: str,
        task_id: str,
        capabilities: AgentCapabilities | None = None,
    ) -> None:
        for name, value in (
            ("engine", engine),
            ("session_id", session_id),
            ("task_id", task_id),
        ):
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{name} must not be empty")
        if capabilities is not None and not isinstance(capabilities, AgentCapabilities):
            raise TypeError("capabilities must be AgentCapabilities or None")
        negotiated = capabilities or AgentCapabilities()
        if treasury.mode.is_blocking and not negotiated.block_actions:
            raise ValueError("enforce mode requires an adapter with block_actions capability")
        self.treasury = treasury
        self.engine = engine
        self.session_id = session_id
        self.task_id = task_id
        self.capabilities = negotiated
        self._pending: dict[str, Action] = {}

    def before_action(self, action: AgentAction) -> AgentDecision:
        if not isinstance(action, AgentAction):
            raise TypeError("action must be AgentAction")
        if action.action_id in self._pending:
            raise ValueError(f"action_id is already pending: {action.action_id}")
        core_action = action.to_core_action(engine=self.engine)
        core_action = replace(
            core_action,
            metadata={
                **dict(core_action.metadata),
                "session_id": self.session_id,
                "task_id": self.task_id,
            },
        )
        decision = self.treasury.authorize(core_action)
        if decision.allowed:
            self._pending[action.action_id] = core_action
        return AgentDecision.from_core(action.action_id, decision)

    def after_action(self, action_id: str, *, actual_cost: Cost | None = None) -> None:
        if actual_cost is not None and not isinstance(actual_cost, Cost):
            raise TypeError("actual_cost must be Cost or None")
        action = self._pop_pending(action_id)
        committed = action if actual_cost is None else replace(action, cost=actual_cost)
        self.treasury.commit(committed)

    def fail_action(
        self,
        action_id: str,
        *,
        reason: str,
        actual_cost: Cost | None = None,
    ) -> None:
        if not isinstance(reason, str) or not reason.strip():
            raise ValueError("reason must not be empty")
        if actual_cost is not None and not isinstance(actual_cost, Cost):
            raise TypeError("actual_cost must be Cost or None")
        action = self._pop_pending(action_id)
        if actual_cost is None:
            self.treasury.abort(action, reason=reason)
        else:
            self.treasury.settle_failure(action, actual_cost, reason=reason)

    def record_outcome(self, outcome: Outcome) -> None:
        if outcome.task_id != self.task_id:
            raise ValueError(
                f"outcome task_id {outcome.task_id!r} does not match runtime "
                f"task_id {self.task_id!r}"
            )
        self.treasury.record_outcome(outcome)

    def pending_action_ids(self) -> tuple[str, ...]:
        return tuple(sorted(self._pending))

    def _pop_pending(self, action_id: str) -> Action:
        try:
            return self._pending.pop(action_id)
        except KeyError as exc:
            raise KeyError(f"unknown or settled action_id: {action_id}") from exc
