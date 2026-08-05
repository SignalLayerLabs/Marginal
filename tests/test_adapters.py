from __future__ import annotations

import pytest

from marginal import Action, BudgetLimits, Cost, MarginalPolicy, PolicyConfig, Treasury
from marginal.adapters import ActionDenied, BudgetedCallable, budgeted_call


def treasury() -> Treasury:
    policy = MarginalPolicy(
        PolicyConfig(outcome_value_usd=10.0, minimum_roi=0.0, target_success_probability=1.0)
    )
    return Treasury(BudgetLimits(max_tokens=1_000, max_usd=1.0), policy=policy)


def test_budgeted_call_executes_and_commits_estimated_cost() -> None:
    calls: list[str] = []

    def operation(value: str) -> str:
        calls.append(value)
        return value.upper()

    action = Action(name="uppercase", kind="tool", cost=Cost(tokens=25), expected_gain=0.1)
    result = budgeted_call(treasury(), operation, action=action, value="hello")

    assert result == "HELLO"
    assert calls == ["hello"]


def test_budgeted_call_does_not_execute_when_denied() -> None:
    called = False

    def operation() -> None:
        nonlocal called
        called = True

    action = Action(name="too large", kind="llm", cost=Cost(tokens=1_001), expected_gain=0.5)

    with pytest.raises(ActionDenied, match="token budget exceeded"):
        budgeted_call(treasury(), operation, action=action)

    assert not called


def test_budgeted_call_commits_actual_usage_from_extractor() -> None:
    class Result:
        pass

    account = treasury()
    action = Action(name="model", kind="llm", cost=Cost(tokens=100), expected_gain=0.2)

    budgeted_call(
        account,
        Result,
        action=action,
        usage_extractor=lambda _result, _estimate: Cost(tokens=40, usd=0.02),
    )

    assert account.usage.tokens == 40
    assert account.usage.usd == pytest.approx(0.02)


def test_budgeted_callable_reuses_configuration() -> None:
    guarded = BudgetedCallable(
        treasury(),
        lambda x, y: x + y,
        action_factory=lambda args, kwargs: Action(
            name="add",
            kind="tool",
            cost=Cost(tokens=1),
            expected_gain=0.1,
            metadata={"args": args, "kwargs": kwargs},
        ),
    )

    assert guarded(2, y=3) == 5


def test_budgeted_call_aborts_authorization_when_callable_raises() -> None:
    account = treasury()
    action = Action(name="flaky", kind="tool", cost=Cost(tokens=900), expected_gain=0.2)

    def fail() -> None:
        raise RuntimeError("boom")

    with pytest.raises(RuntimeError, match="boom"):
        budgeted_call(account, fail, action=action)

    assert account.authorize(action).allowed


def test_common_usage_extractor_preserves_unobserved_cost_dimensions() -> None:
    from marginal.adapters import extract_common_llm_usage

    result = {"usage": {"input_tokens": 30, "output_tokens": 10}}
    estimated = Cost(tokens=100, usd=0.08, latency_ms=500, risk=0.02)

    actual = extract_common_llm_usage(result, estimated)

    assert actual == Cost(tokens=40, usd=0.08, latency_ms=500, risk=0.02)


def test_actual_overrun_is_accounted_before_error_is_raised() -> None:
    from marginal import BudgetOverrun

    account = treasury()
    action = Action(name="underestimated", kind="llm", cost=Cost(tokens=900), expected_gain=0.2)

    with pytest.raises(BudgetOverrun, match="token budget exceeded"):
        budgeted_call(
            account,
            lambda: {"usage": {"total_tokens": 1_100}},
            action=action,
            usage_extractor=lambda result, estimate: Cost(
                tokens=result["usage"]["total_tokens"],
                usd=estimate.usd,
            ),
        )

    assert account.usage.tokens == 1_100


def test_budgeted_call_distinguishes_different_inputs() -> None:
    account = treasury()
    action = Action(name="transform", kind="tool", cost=Cost(tokens=10), expected_gain=0.2)

    first = budgeted_call(account, str.upper, "first", action=action)
    second = budgeted_call(account, str.upper, "second", action=action)

    assert first == "FIRST"
    assert second == "SECOND"
    assert account.summary()["committed"] == 2


def test_budgeted_call_rejects_an_exact_repeated_call() -> None:
    account = treasury()
    action = Action(name="transform", kind="tool", cost=Cost(tokens=10), expected_gain=0.2)

    budgeted_call(account, str.upper, "same", action=action)

    with pytest.raises(ActionDenied, match="duplicate action"):
        budgeted_call(account, str.upper, "same", action=action)


def test_async_budgeted_call_executes_and_commits() -> None:
    import asyncio

    from marginal.adapters import async_budgeted_call

    account = treasury()
    action = Action(name="async", kind="tool", cost=Cost(tokens=25), expected_gain=0.2)

    async def operation(value: str) -> str:
        return value.upper()

    result = asyncio.run(async_budgeted_call(account, operation, "hello", action=action))

    assert result == "HELLO"
    assert account.usage.tokens == 25


def test_async_budgeted_call_releases_reservation_on_failure() -> None:
    import asyncio

    from marginal.adapters import async_budgeted_call

    account = treasury()
    action = Action(name="async failure", kind="tool", cost=Cost(tokens=900), expected_gain=0.2)

    async def fail() -> None:
        raise RuntimeError("async boom")

    with pytest.raises(RuntimeError, match="async boom"):
        asyncio.run(async_budgeted_call(account, fail, action=action))

    assert account.authorize(action).allowed


def test_common_usage_extractor_rejects_unrecognized_usage_shape() -> None:
    from marginal.adapters import extract_common_llm_usage

    with pytest.raises(ValueError, match="recognized token fields"):
        extract_common_llm_usage({"usage": {"requests": 1}}, Cost(tokens=100))


def test_usage_extractor_failure_settles_estimate_before_reraising() -> None:
    account = treasury()
    action = Action(name="unknown usage", kind="llm", cost=Cost(tokens=100), expected_gain=0.2)

    def fail_usage(_result: object, _estimate: Cost) -> Cost:
        raise ValueError("usage failed")

    with pytest.raises(ValueError, match="usage failed"):
        budgeted_call(
            account,
            lambda: object(),
            action=action,
            usage_extractor=fail_usage,
        )

    assert account.usage.tokens == 100
    assert account.summary()["committed"] == 1


def test_usage_extractor_must_return_cost() -> None:
    account = treasury()
    action = Action(name="invalid usage", kind="llm", cost=Cost(tokens=100), expected_gain=0.2)

    with pytest.raises(TypeError, match="usage_extractor must return Cost"):
        budgeted_call(
            account,
            lambda: object(),
            action=action,
            usage_extractor=lambda _result, _estimate: {"tokens": 20},  # type: ignore[return-value]
        )

    assert account.usage.tokens == 100
    assert account.summary()["committed"] == 1


def test_common_usage_extractor_rejects_boolean_token_counts() -> None:
    from marginal.adapters import extract_common_llm_usage

    with pytest.raises(TypeError, match="token fields must be integers"):
        extract_common_llm_usage({"usage": {"total_tokens": True}}, Cost(tokens=100))


def test_funded_call_executes_reserved_allocation_and_commits() -> None:
    from marginal.adapters import funded_call

    account = treasury()
    allocation = account.fund_best(
        [Action(name="funded", kind="tool", cost=Cost(tokens=25), expected_gain=0.2)]
    )
    assert allocation is not None

    result = funded_call(account, allocation, str.upper, "hello")

    assert result == "HELLO"
    assert account.usage.tokens == 25
    assert account.ledger.reserved_usage.tokens == 0


def test_funded_call_aborts_reserved_allocation_on_failure() -> None:
    from marginal.adapters import funded_call

    account = treasury()
    allocation = account.fund_best(
        [Action(name="funded failure", kind="tool", cost=Cost(tokens=900), expected_gain=0.2)]
    )
    assert allocation is not None

    def fail() -> None:
        raise RuntimeError("funded boom")

    with pytest.raises(RuntimeError, match="funded boom"):
        funded_call(account, allocation, fail)

    assert account.ledger.reserved_usage.tokens == 0
    assert account.authorize(allocation.action).allowed


def test_async_funded_call_executes_reserved_allocation() -> None:
    import asyncio

    from marginal.adapters import async_funded_call

    account = treasury()
    allocation = account.fund_best(
        [Action(name="async funded", kind="tool", cost=Cost(tokens=25), expected_gain=0.2)]
    )
    assert allocation is not None

    async def operation(value: str) -> str:
        return value.upper()

    result = asyncio.run(async_funded_call(account, allocation, operation, "hello"))

    assert result == "HELLO"
    assert account.usage.tokens == 25


def test_funded_call_does_not_execute_unreserved_allocation() -> None:
    from marginal import Allocation, Decision
    from marginal.adapters import funded_call
    from marginal.treasury import AuthorizationRequired

    called = False

    def operation() -> None:
        nonlocal called
        called = True

    action = Action(name="unreserved", kind="tool", cost=Cost(tokens=10), expected_gain=0.2)
    allocation = Allocation(action=action, decision=Decision(True, "manually constructed"))

    with pytest.raises(AuthorizationRequired, match="must be authorized"):
        funded_call(treasury(), allocation, operation)

    assert not called


def test_callable_error_remains_primary_when_abort_trace_fails() -> None:
    account_events = 0

    class AbortFailingTrace:
        def emit(self, event) -> None:
            nonlocal account_events
            account_events += 1
            if event["event"] == "abort":
                raise OSError("abort trace unavailable")

    account = Treasury(
        BudgetLimits(max_tokens=100),
        policy=MarginalPolicy(
            PolicyConfig(outcome_value_usd=10.0, minimum_roi=0.0)
        ),
        trace_sink=AbortFailingTrace(),
    )
    action = Action(name="operation failure", kind="tool", cost=Cost(tokens=10), expected_gain=0.2)

    def fail() -> None:
        raise RuntimeError("original failure")

    with pytest.raises(RuntimeError, match="original failure") as captured:
        budgeted_call(account, fail, action=action)

    assert isinstance(captured.value.__cause__, OSError)
    assert account.ledger.reserved_usage.tokens == 0
    assert account_events == 2
