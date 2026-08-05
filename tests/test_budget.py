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


def test_verification_action_can_use_reserved_budget() -> None:
    ledger = BudgetLedger(
        BudgetLimits(max_tokens=1_000, max_usd=1.0, verification_reserve_tokens=200)
    )
    regular = Action(name="draft", kind="generation", cost=Cost(tokens=800, usd=0.20))
    verifier = Action(
        name="run tests",
        kind="verification",
        cost=Cost(tokens=200, usd=0.05),
        is_verification=True,
    )

    assert ledger.can_afford(regular).allowed
    ledger.commit(regular)
    assert ledger.can_afford(verifier).allowed


def test_denied_action_does_not_consume_budget() -> None:
    ledger = BudgetLedger(BudgetLimits(max_tokens=100, max_usd=1.0))
    too_large = Action(name="large", kind="generation", cost=Cost(tokens=101, usd=0.1))

    before = ledger.usage
    affordability = ledger.can_afford(too_large)
    after = ledger.usage

    assert not affordability.allowed
    assert before == after
    assert after.tokens == 0
    assert after.usd == 0.0


def test_commit_tracks_tokens_usd_latency_and_risk() -> None:
    ledger = BudgetLedger(BudgetLimits(max_tokens=500, max_usd=2.0, max_latency_ms=10_000))
    action = Action(
        name="call model",
        kind="llm",
        cost=Cost(tokens=120, usd=0.03, latency_ms=350, risk=0.04),
    )

    ledger.commit(action)

    assert ledger.usage.tokens == 120
    assert ledger.usage.usd == pytest.approx(0.03)
    assert ledger.usage.latency_ms == 350
    assert ledger.usage.risk == pytest.approx(0.04)


def test_regular_budget_remains_available_after_reserved_verification_is_spent() -> None:
    ledger = BudgetLedger(
        BudgetLimits(max_tokens=1_000, max_usd=1.0, verification_reserve_tokens=200)
    )
    verifier = Action(
        name="verify first",
        kind="verification",
        cost=Cost(tokens=200),
        is_verification=True,
    )
    regular = Action(name="finish work", kind="generation", cost=Cost(tokens=800))

    ledger.commit(verifier)

    assert ledger.can_afford(regular).allowed


def test_reservations_reduce_available_budget_before_commit() -> None:
    ledger = BudgetLedger(BudgetLimits(max_tokens=100))
    first = Action(name="first", kind="tool", cost=Cost(tokens=70), fingerprint="first")
    second = Action(name="second", kind="tool", cost=Cost(tokens=40), fingerprint="second")

    ledger.reserve(first)

    assert ledger.usage.tokens == 0
    assert ledger.reserved_usage.tokens == 70
    assert not ledger.can_afford(second).allowed


def test_releasing_reservation_restores_available_budget() -> None:
    ledger = BudgetLedger(BudgetLimits(max_tokens=100))
    action = Action(name="first", kind="tool", cost=Cost(tokens=70), fingerprint="first")

    ledger.reserve(action)
    ledger.release("first")

    assert ledger.reserved_usage.tokens == 0
    assert ledger.can_afford(action).allowed


def test_cost_rejects_non_integer_counters_and_non_finite_values() -> None:
    with pytest.raises(TypeError, match="tokens must be an integer"):
        Cost(tokens=1.5)  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="latency_ms must be an integer"):
        Cost(latency_ms=True)  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="finite"):
        Cost(usd=float("nan"))


def test_budget_limits_reject_invalid_numeric_types() -> None:
    with pytest.raises(TypeError, match="max_tokens must be an integer"):
        BudgetLimits(max_tokens=10.5)  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="finite"):
        BudgetLimits(max_usd=float("inf"))


def test_action_rejects_invalid_public_fields() -> None:
    with pytest.raises(TypeError, match="name must be a string"):
        Action(name=1, kind="tool")  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="cost must be Cost"):
        Action(name="bad cost", kind="tool", cost={})  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="is_verification must be a boolean"):
        Action(name="bad flag", kind="tool", is_verification=1)  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="fingerprint must not be empty"):
        Action(name="bad fingerprint", kind="tool", fingerprint="  ")


def test_verification_reserve_requires_corresponding_hard_limit() -> None:
    with pytest.raises(ValueError, match="token reserve requires max_tokens"):
        BudgetLimits(verification_reserve_tokens=1)
    with pytest.raises(ValueError, match="USD reserve requires max_usd"):
        BudgetLimits(verification_reserve_usd=0.01)
