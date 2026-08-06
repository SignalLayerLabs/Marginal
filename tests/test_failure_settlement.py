from __future__ import annotations

import asyncio

import pytest

from marginal import Action, BudgetLimits, Cost, MarginalPolicy, PolicyConfig, Treasury
from marginal.adapters import async_budgeted_call, budgeted_call


def account() -> Treasury:
    return Treasury(
        BudgetLimits(max_tokens=100),
        policy=MarginalPolicy(PolicyConfig(outcome_value_usd=10.0, minimum_roi=0.0)),
    )


def test_sync_failure_can_settle_measured_usage_and_preserve_original_error() -> None:
    treasury = account()
    action = Action(name="remote call", kind="llm", cost=Cost(tokens=50), expected_gain=0.5)

    def fail() -> None:
        raise RuntimeError("provider disconnected")

    with pytest.raises(RuntimeError, match="provider disconnected"):
        budgeted_call(
            treasury,
            fail,
            action=action,
            failure_usage_extractor=lambda _error, _estimate: Cost(tokens=30),
        )
    assert treasury.usage.tokens == 30
    assert treasury.summary()["failed_settled"] == 1


def test_failure_extractor_none_releases_reservation() -> None:
    treasury = account()
    action = Action(name="local failure", kind="tool", cost=Cost(tokens=50), expected_gain=0.5)

    def fail() -> None:
        raise RuntimeError("no spend")

    with pytest.raises(RuntimeError, match="no spend"):
        budgeted_call(
            treasury,
            fail,
            action=action,
            failure_usage_extractor=lambda _error, _estimate: None,
        )
    assert treasury.usage.tokens == 0
    assert treasury.summary()["aborted"] == 1


def test_async_failure_settles_usage() -> None:
    treasury = account()
    action = Action(name="async remote", kind="llm", cost=Cost(tokens=50), expected_gain=0.5)

    async def fail() -> None:
        raise RuntimeError("async provider disconnected")

    with pytest.raises(RuntimeError, match="async provider disconnected"):
        asyncio.run(
            async_budgeted_call(
                treasury,
                fail,
                action=action,
                failure_usage_extractor=lambda _error, _estimate: Cost(tokens=25),
            )
        )
    assert treasury.usage.tokens == 25


def test_failed_settlement_does_not_mark_action_as_completed_duplicate() -> None:
    treasury = account()
    action = Action(name="retryable remote", kind="llm", cost=Cost(tokens=50), expected_gain=0.5)

    prepared = action
    decision = treasury.authorize(prepared)
    assert decision.allowed
    treasury.settle_failure(prepared, Cost(tokens=20), reason="timeout")

    retry = treasury.authorize(action)

    assert retry.allowed


def test_failure_usage_extractor_error_settles_estimate_and_preserves_original_error() -> None:
    treasury = account()
    action = Action(
        name="unknown remote failure",
        kind="llm",
        cost=Cost(tokens=50),
        expected_gain=0.5,
    )

    def fail() -> None:
        raise RuntimeError("provider failed")

    def broken_extractor(_error: Exception, _estimate: Cost) -> Cost | None:
        raise ValueError("usage unavailable")

    with pytest.raises(RuntimeError, match="provider failed") as captured:
        budgeted_call(
            treasury,
            fail,
            action=action,
            failure_usage_extractor=broken_extractor,
        )

    assert isinstance(captured.value.__cause__, ValueError)
    assert treasury.usage.tokens == 50
    assert treasury.ledger.reserved_usage.tokens == 0
