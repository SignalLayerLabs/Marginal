from __future__ import annotations

import pytest

from marginal.budget import BudgetLedger, BudgetLimits
from marginal.models import Action, Cost


def test_cost_rejects_negative_values() -> None:
    with pytest.raises(ValueError, match="non-negative"):
        Cost(tokens=-1)


def test_regular_action_cannot_spend_verification_reserve() -> None:
    ledger = BudgetLedger(
        BudgetLimits(max_tokens=1_000, max_usd=1.0, verification_reserve_tokens=200)
    )
    action = Action(name="research", kind="research", cost=Cost(tokens=850, usd=0.10))
    affordability = ledger.can_afford(action)
    assert not affordability.allowed
    assert affordability.reason == "verification reserve would be breached"


def test_reservations_reduce_available_budget_before_commit() -> None:
    ledger = BudgetLedger(BudgetLimits(max_tokens=100))
    first = Action(name="first", kind="tool", cost=Cost(tokens=70), fingerprint="first")
    second = Action(name="second", kind="tool", cost=Cost(tokens=40), fingerprint="second")
    ledger.reserve(first)
    assert ledger.usage.tokens == 0
    assert ledger.reserved_usage.tokens == 70
    assert not ledger.can_afford(second).allowed


def test_verification_spend_does_not_reduce_regular_limit_unnecessarily() -> None:
    ledger = BudgetLedger(BudgetLimits(max_tokens=1_000, verification_reserve_tokens=200))
    ledger.commit(
        Action(
            name="verify",
            kind="verification",
            cost=Cost(tokens=200),
            is_verification=True,
        )
    )
    assert ledger.can_afford(
        Action(name="finish", kind="generation", cost=Cost(tokens=800))
    ).allowed
