"""High-level orchestration for budgeted agent execution."""

from __future__ import annotations

import threading
from collections.abc import Iterable
from dataclasses import asdict, replace
from typing import Any

from .budget import BudgetLedger, BudgetLimits, BudgetOverrun, BudgetUsage
from .fingerprint import fingerprint_action
from .models import Action, Allocation, Cost, Decision
from .modes import ExecutionMode
from .outcomes import Outcome
from .policy import MarginalPolicy
from .trace import NullTraceSink, TraceSink, action_payload, decision_payload, usage_payload


class AuthorizationRequired(RuntimeError):
    """Raised when settling or aborting an action that was not authorized."""


class Treasury:
    """Allocate and account for agent compute as a scarce resource."""

    def __init__(
        self,
        limits: BudgetLimits,
        *,
        policy: MarginalPolicy | None = None,
        trace_sink: TraceSink | None = None,
        name: str = "root",
        parent: Treasury | None = None,
        mode: ExecutionMode | str = ExecutionMode.ENFORCE,
    ) -> None:
        self.name = name
        self.ledger = BudgetLedger(limits)
        self.policy = policy or MarginalPolicy()
        self.trace_sink = trace_sink or NullTraceSink()
        self.parent = parent
        self.mode = ExecutionMode.parse(mode)
        self._lock: threading.RLock = parent._lock if parent is not None else threading.RLock()
        self._root: Treasury = parent._root if parent is not None else self
        self._pending: dict[str, Treasury] = parent._pending if parent is not None else {}
        self._pending_semantics: dict[str, list[str]] = (
            parent._pending_semantics if parent is not None else {}
        )
        if parent is None:
            self._reservation_counter = 0
        self._approved_count = 0
        self._denied_count = 0
        self._committed_count = 0
        self._aborted_count = 0
        self._observed_overruns = 0
        self._failed_settled_count = 0
        self._outcome_count = 0
        self._observation_count = 0

    @property
    def usage(self) -> BudgetUsage:
        return self.ledger.usage

    @property
    def limits(self) -> BudgetLimits:
        return self.ledger.limits

    def propose(self, action: Action) -> Decision:
        return self.authorize(action)

    def evaluate(self, action: Action) -> Decision:
        """Evaluate an action without reserving resources or mutating counters."""

        prepared = self._prepare(action)
        assert prepared.fingerprint is not None
        with self._lock:
            return self._recommended_decision(prepared)

    def is_authorized(self, action: Action) -> bool:
        prepared = self._prepare(action)
        assert prepared.fingerprint is not None
        with self._lock:
            return self._owned_reservation_fingerprint(prepared.fingerprint) is not None

    def fund_best(self, actions: Iterable[Action]) -> Allocation | None:
        """Evaluate candidates and reserve the recommended highest-value candidate.

        This remains an active allocation API in every mode. Shadow mode applies to a
        proposed action supplied by an external agent; it does not invent an uncontrolled
        baseline candidate when MARGINAL itself is asked to choose.
        """

        with self._lock:
            candidates: list[tuple[Action, Decision]] = []
            evaluated: list[dict[str, Any]] = []
            for action in actions:
                prepared = self._prepare(action)
                assert prepared.fingerprint is not None
                decision = self._recommended_decision(prepared)
                evaluated.append(
                    {
                        "action": action_payload(prepared),
                        "decision": decision_payload(decision),
                    }
                )
                if decision.allowed:
                    candidates.append((prepared, decision))

            self.trace_sink.emit(
                {
                    **self._identity_payload(),
                    "event": "candidate_ranking",
                    "treasury": self.name,
                    "candidates": evaluated,
                }
            )
            if not candidates:
                return None

            prepared, _ = max(
                candidates,
                key=lambda item: (
                    item[1].score,
                    item[1].expected_gain,
                    -item[1].estimated_cost_value,
                    item[0].fingerprint or "",
                ),
            )
            decision = self.authorize(prepared, apply_mode=False)
            if not decision.allowed:
                return None
            return Allocation(action=prepared, decision=decision)

    def authorize(self, action: Action, *, apply_mode: bool = True) -> Decision:
        prepared = self._prepare(action)
        assert prepared.fingerprint is not None
        with self._lock:
            recommended = self._recommended_decision(prepared)
            decision = self._apply_mode(recommended) if apply_mode else recommended

            reservation_action: Action | None = None
            if decision.allowed:
                reservation_action = self._reservation_action(prepared)
                for ledger in self._ledger_chain():
                    if self.mode.is_blocking or not apply_mode:
                        ledger.reserve(reservation_action)
                    else:
                        ledger.reserve_unchecked(reservation_action)
                self._register_pending(prepared.fingerprint, reservation_action.fingerprint)
                self._approved_count += 1
            else:
                self._denied_count += 1

            try:
                self.trace_sink.emit(
                    {
                        **self._identity_payload(),
                        "event": "authorization",
                        "treasury": self.name,
                        "action": action_payload(prepared),
                        "decision": decision_payload(decision),
                        "usage": usage_payload(self.usage),
                        "reserved": usage_payload(self.ledger.reserved_usage),
                    }
                )
            except Exception:
                if decision.allowed:
                    assert reservation_action is not None
                    assert reservation_action.fingerprint is not None
                    for ledger in self._ledger_chain():
                        ledger.release(reservation_action.fingerprint)
                    self._unregister_pending(
                        prepared.fingerprint,
                        reservation_action.fingerprint,
                    )
                    self._approved_count -= 1
                else:
                    self._denied_count -= 1
                raise
            return decision

    def commit(self, action: Action) -> BudgetUsage:
        return self._settle(action, failed=False, failure_reason="")

    def settle_failure(
        self,
        action: Action,
        actual_cost: Cost,
        *,
        reason: str,
    ) -> BudgetUsage:
        """Account measured external spend from a failed action without hiding its error."""

        if not isinstance(actual_cost, Cost):
            raise TypeError("actual_cost must be Cost")
        prepared = self._prepare(action)
        committed = replace(prepared, cost=actual_cost)
        return self._settle(committed, failed=True, failure_reason=reason)

    def _settle(
        self,
        action: Action,
        *,
        failed: bool,
        failure_reason: str,
    ) -> BudgetUsage:
        prepared = self._prepare(action)
        assert prepared.fingerprint is not None
        with self._lock:
            reservation_fingerprint = self._owned_reservation_fingerprint(prepared.fingerprint)
            if reservation_fingerprint is None:
                raise AuthorizationRequired(
                    "action must be authorized by this treasury before commit"
                )

            violations: list[str] = []
            for ledger in self._ledger_chain():
                decision = ledger.settle(
                    prepared,
                    reservation_fingerprint=reservation_fingerprint,
                )
                if not decision.allowed:
                    violations.append(decision.reason)

            if not failed:
                self.policy.mark_executed(prepared.fingerprint)
            self._unregister_pending(prepared.fingerprint, reservation_fingerprint)
            self._committed_count += 1
            if failed:
                self._failed_settled_count += 1
            if violations and not self.mode.is_blocking:
                self._observed_overruns += 1

            event = {
                **self._identity_payload(),
                "event": "failure_settlement" if failed else "commit",
                "treasury": self.name,
                "action": action_payload(prepared),
                "usage": usage_payload(self.usage),
                "budget_overrun": bool(violations),
                "violations": sorted(set(violations)),
            }
            if failed:
                event["reason"] = failure_reason
            self.trace_sink.emit(event)

            if violations and self.mode.is_blocking and not failed:
                raise BudgetOverrun("; ".join(sorted(set(violations))))
            return self.usage

    def abort(self, action: Action, *, reason: str = "execution aborted") -> None:
        prepared = self._prepare(action)
        assert prepared.fingerprint is not None
        with self._lock:
            reservation_fingerprint = self._owned_reservation_fingerprint(prepared.fingerprint)
            if reservation_fingerprint is None:
                raise AuthorizationRequired(
                    "action must be authorized by this treasury before abort"
                )
            for ledger in self._ledger_chain():
                ledger.release(reservation_fingerprint)
            self._unregister_pending(prepared.fingerprint, reservation_fingerprint)
            self._aborted_count += 1
            self.trace_sink.emit(
                {
                    **self._identity_payload(),
                    "event": "abort",
                    "treasury": self.name,
                    "action": action_payload(prepared),
                    "reason": reason,
                    "usage": usage_payload(self.usage),
                }
            )

    def observe_value(self, action: Action, realized_gain: float) -> None:
        """Record explicit action-level realized gain for the configured estimator."""

        observe = getattr(self.policy.estimator, "observe_action", None)
        if not callable(observe):
            raise TypeError("configured estimator does not support action observations")
        observe(action, realized_gain)
        self._observation_count += 1
        self.trace_sink.emit(
            {
                **self._identity_payload(),
                "event": "estimator_observation",
                "treasury": self.name,
                "action": action_payload(self._prepare(action)),
                "realized_gain": float(realized_gain),
            }
        )

    def record_outcome(self, outcome: Outcome) -> None:
        """Record a verified task outcome without inferring individual action causality."""

        if not isinstance(outcome, Outcome):
            raise TypeError("outcome must be Outcome")
        self._outcome_count += 1
        try:
            self.trace_sink.emit(
                {
                    **self._identity_payload(),
                    "event": "outcome",
                    "treasury": self.name,
                    "outcome": outcome.to_dict(),
                }
            )
        except Exception:
            self._outcome_count -= 1
            raise

    def child(self, name: str, limits: BudgetLimits) -> Treasury:
        if not name.strip():
            raise ValueError("child treasury name must not be empty")
        return Treasury(
            limits,
            policy=self.policy,
            trace_sink=self.trace_sink,
            name=f"{self.name}/{name}",
            parent=self,
            mode=self.mode,
        )

    def summary(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "mode": self.mode.value,
            "approved": self._approved_count,
            "denied": self._denied_count,
            "committed": self._committed_count,
            "aborted": self._aborted_count,
            "observed_overruns": self._observed_overruns,
            "failed_settled": self._failed_settled_count,
            "outcomes": self._outcome_count,
            "estimator_observations": self._observation_count,
            "usage": asdict(self.usage),
            "reserved": asdict(self.ledger.reserved_usage),
            "limits": asdict(self.limits),
            "policy": self.policy.identity.to_dict(),
            "estimator": self.policy.estimator_identity.to_dict(),
        }

    def _recommended_decision(self, prepared: Action) -> Decision:
        assert prepared.fingerprint is not None
        if self._pending_semantics.get(prepared.fingerprint):
            return Decision(
                False,
                "rejected: duplicate pending action",
                recommended=False,
                recommendation_reason="rejected: duplicate pending action",
                reason_code="DUPLICATE_PENDING",
                recommendation_reason_code="DUPLICATE_PENDING",
                estimator_name=self.policy.estimator_identity.name,
                estimator_version=self.policy.estimator_identity.version,
            )

        decision = self.policy.evaluate(prepared, self.ledger)
        if decision.allowed:
            for ancestor in self._ancestors():
                affordability = ancestor.ledger.can_afford(prepared)
                if not affordability.allowed:
                    return replace(
                        decision,
                        allowed=False,
                        recommended=False,
                        reason=f"rejected by parent: {affordability.reason}",
                        recommendation_reason=f"rejected by parent: {affordability.reason}",
                        reason_code="PARENT_BUDGET_REJECTED",
                        recommendation_reason_code="PARENT_BUDGET_REJECTED",
                    )
        return decision

    def _apply_mode(self, recommended: Decision) -> Decision:
        if self.mode.is_blocking:
            return replace(
                recommended,
                mode=self.mode.value,
                recommended=recommended.allowed,
                recommendation_reason=recommended.reason,
                recommendation_reason_code=recommended.reason_code,
            )
        if recommended.allowed:
            return replace(
                recommended,
                mode=self.mode.value,
                recommended=True,
                recommendation_reason=recommended.reason,
                recommendation_reason_code=recommended.reason_code,
            )
        return replace(
            recommended,
            allowed=True,
            recommended=False,
            reason=(
                f"{self.mode.value}: action executed; recommendation was deny "
                f"({recommended.reason})"
            ),
            reason_code=f"{self.mode.value.upper()}_OVERRIDE",
            recommendation_reason=recommended.reason,
            recommendation_reason_code=recommended.reason_code,
            mode=self.mode.value,
        )

    def _reservation_action(self, prepared: Action) -> Action:
        assert prepared.fingerprint is not None
        if not self._pending_semantics.get(prepared.fingerprint):
            return prepared
        self._root._reservation_counter += 1
        reservation_fingerprint = (
            f"{prepared.fingerprint}:reservation:{self._root._reservation_counter}"
        )
        return replace(prepared, fingerprint=reservation_fingerprint)

    def _register_pending(
        self,
        semantic_fingerprint: str,
        reservation_fingerprint: str | None,
    ) -> None:
        if reservation_fingerprint is None:
            raise ValueError("reservation fingerprint must not be empty")
        self._pending[reservation_fingerprint] = self
        self._pending_semantics.setdefault(semantic_fingerprint, []).append(reservation_fingerprint)

    def _unregister_pending(
        self,
        semantic_fingerprint: str,
        reservation_fingerprint: str,
    ) -> None:
        del self._pending[reservation_fingerprint]
        reservations = self._pending_semantics[semantic_fingerprint]
        reservations.remove(reservation_fingerprint)
        if not reservations:
            del self._pending_semantics[semantic_fingerprint]

    def _owned_reservation_fingerprint(
        self,
        semantic_fingerprint: str,
    ) -> str | None:
        for reservation_fingerprint in self._pending_semantics.get(semantic_fingerprint, ()):
            if self._pending.get(reservation_fingerprint) is self:
                return reservation_fingerprint
        return None

    def _identity_payload(self) -> dict[str, Any]:
        return {
            "mode": self.mode.value,
            "policy": self.policy.identity.to_dict(),
            "estimator": self.policy.estimator_identity.to_dict(),
        }

    def _prepare(self, action: Action) -> Action:
        if action.fingerprint:
            return action
        return replace(action, fingerprint=fingerprint_action(action))

    def _ledger_chain(self) -> list[BudgetLedger]:
        ledgers = [self.ledger]
        current = self.parent
        while current is not None:
            ledgers.append(current.ledger)
            current = current.parent
        return ledgers

    def _ancestors(self) -> list[Treasury]:
        ancestors: list[Treasury] = []
        current = self.parent
        while current is not None:
            ancestors.append(current)
            current = current.parent
        return ancestors
