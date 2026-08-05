"""High-level orchestration for budgeted agent execution."""

from __future__ import annotations

import threading
from collections.abc import Iterable
from dataclasses import asdict, replace
from typing import Any

from .budget import BudgetLedger, BudgetLimits, BudgetOverrun, BudgetUsage
from .fingerprint import fingerprint_action
from .models import Action, Allocation, Decision
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
    ) -> None:
        self.name = name
        self.ledger = BudgetLedger(limits)
        self.policy = policy or MarginalPolicy()
        self.trace_sink = trace_sink or NullTraceSink()
        self.parent = parent
        self._lock = parent._lock if parent is not None else threading.RLock()
        self._pending: dict[str, Treasury] = parent._pending if parent is not None else {}
        self._approved_count = 0
        self._denied_count = 0
        self._committed_count = 0
        self._aborted_count = 0

    @property
    def usage(self) -> BudgetUsage:
        return self.ledger.usage

    @property
    def limits(self) -> BudgetLimits:
        return self.ledger.limits

    def propose(self, action: Action) -> Decision:
        return self.authorize(action)

    def is_authorized(self, action: Action) -> bool:
        """Return whether an action currently owns a pending reservation."""

        prepared = self._prepare(action)
        assert prepared.fingerprint is not None
        with self._lock:
            return self._pending.get(prepared.fingerprint) is self

    def fund_best(self, actions: Iterable[Action]) -> Allocation | None:
        """Evaluate candidates and reserve the one with the highest marginal score."""

        with self._lock:
            candidates: list[tuple[Action, Decision]] = []
            evaluated: list[dict[str, Any]] = []
            for action in actions:
                prepared = self._prepare(action)
                assert prepared.fingerprint is not None
                if prepared.fingerprint in self._pending:
                    decision = Decision(False, "rejected: duplicate pending action")
                else:
                    decision = self.policy.evaluate(prepared, self.ledger)
                if decision.allowed:
                    for ancestor in self._ancestors():
                        affordability = ancestor.ledger.can_afford(prepared)
                        if not affordability.allowed:
                            decision = Decision(
                                False,
                                f"rejected by parent: {affordability.reason}",
                            )
                            break
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
            decision = self.authorize(prepared)
            if not decision.allowed:
                return None
            return Allocation(action=prepared, decision=decision)

    def authorize(self, action: Action) -> Decision:
        prepared = self._prepare(action)
        assert prepared.fingerprint is not None
        with self._lock:
            if prepared.fingerprint in self._pending:
                decision = Decision(False, "rejected: duplicate pending action")
            else:
                decision = self.policy.evaluate(prepared, self.ledger)

            if decision.allowed:
                for ancestor in self._ancestors():
                    affordability = ancestor.ledger.can_afford(prepared)
                    if not affordability.allowed:
                        decision = Decision(
                            False,
                            f"rejected by parent: {affordability.reason}",
                        )
                        break

            if decision.allowed:
                for ledger in self._ledger_chain():
                    ledger.reserve(prepared)
                self._pending[prepared.fingerprint] = self
                self._approved_count += 1
            else:
                self._denied_count += 1

            try:
                self.trace_sink.emit(
                    {
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
                    for ledger in self._ledger_chain():
                        ledger.release(prepared.fingerprint)
                    del self._pending[prepared.fingerprint]
                    self._approved_count -= 1
                else:
                    self._denied_count -= 1
                raise
            return decision

    def commit(self, action: Action) -> BudgetUsage:
        prepared = self._prepare(action)
        assert prepared.fingerprint is not None
        with self._lock:
            if self._pending.get(prepared.fingerprint) is not self:
                raise AuthorizationRequired(
                    "action must be authorized by this treasury before commit"
                )

            violations: list[str] = []
            for ledger in self._ledger_chain():
                decision = ledger.settle(
                    prepared,
                    reservation_fingerprint=prepared.fingerprint,
                )
                if not decision.allowed:
                    violations.append(decision.reason)

            self.policy.mark_executed(prepared.fingerprint)
            del self._pending[prepared.fingerprint]
            self._committed_count += 1
            self.trace_sink.emit(
                {
                    "event": "commit",
                    "treasury": self.name,
                    "action": action_payload(prepared),
                    "usage": usage_payload(self.usage),
                    "budget_overrun": bool(violations),
                    "violations": sorted(set(violations)),
                }
            )
            if violations:
                raise BudgetOverrun("; ".join(sorted(set(violations))))
            return self.usage

    def abort(self, action: Action, *, reason: str = "execution aborted") -> None:
        """Release all reservations for an authorized action without recording spend."""

        prepared = self._prepare(action)
        assert prepared.fingerprint is not None
        with self._lock:
            if self._pending.get(prepared.fingerprint) is not self:
                raise AuthorizationRequired(
                    "action must be authorized by this treasury before abort"
                )
            for ledger in self._ledger_chain():
                ledger.release(prepared.fingerprint)
            del self._pending[prepared.fingerprint]
            self._aborted_count += 1
            self.trace_sink.emit(
                {
                    "event": "abort",
                    "treasury": self.name,
                    "action": action_payload(prepared),
                    "reason": reason,
                    "usage": usage_payload(self.usage),
                }
            )

    def child(self, name: str, limits: BudgetLimits) -> Treasury:
        if not name.strip():
            raise ValueError("child treasury name must not be empty")
        return Treasury(
            limits,
            policy=self.policy,
            trace_sink=self.trace_sink,
            name=f"{self.name}/{name}",
            parent=self,
        )

    def summary(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "approved": self._approved_count,
            "denied": self._denied_count,
            "committed": self._committed_count,
            "aborted": self._aborted_count,
            "usage": asdict(self.usage),
            "reserved": asdict(self.ledger.reserved_usage),
            "limits": asdict(self.limits),
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
