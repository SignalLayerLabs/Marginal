from __future__ import annotations

import pytest

from marginal import Action, BudgetLimits, Cost, MarginalPolicy, PolicyConfig, Treasury
from marginal.adapters import ActionDenied, budgeted_call, extract_common_llm_usage


def treasury() -> Treasury:
    return Treasury(
        BudgetLimits(max_tokens=1_000, max_usd=1.0),
        policy=MarginalPolicy(PolicyConfig(outcome_value_usd=10.0, minimum_roi=0.0)),
    )


def test_budgeted_call_does_not_execute_when_denied() -> None:
    called = False

    def operation() -> None:
        nonlocal called
        called = True

    with pytest.raises(ActionDenied):
        budgeted_call(
            treasury(),
            operation,
            action=Action(name="too large", kind="llm", cost=Cost(tokens=1_001), expected_gain=0.5),
        )
    assert not called


def test_budgeted_call_commits_actual_usage_from_extractor() -> None:
    account = treasury()
    budgeted_call(
        account,
        lambda: {"usage": {"total_tokens": 40}},
        action=Action(name="model", kind="llm", cost=Cost(tokens=100), expected_gain=0.2),
        usage_extractor=lambda result, _estimate: Cost(tokens=result["usage"]["total_tokens"]),
    )
    assert account.usage.tokens == 40


def test_common_usage_extractor_preserves_unobserved_dimensions() -> None:
    actual = extract_common_llm_usage(
        {"usage": {"input_tokens": 30, "output_tokens": 10}},
        Cost(tokens=100, usd=0.08, latency_ms=500, risk=0.02),
    )
    assert actual == Cost(tokens=40, usd=0.08, latency_ms=500, risk=0.02)


def test_exact_repeated_call_is_rejected() -> None:
    account = treasury()
    action = Action(name="transform", kind="tool", cost=Cost(tokens=10), expected_gain=0.2)
    budgeted_call(account, str.upper, "same", action=action)
    with pytest.raises(ActionDenied, match="duplicate action"):
        budgeted_call(account, str.upper, "same", action=action)
