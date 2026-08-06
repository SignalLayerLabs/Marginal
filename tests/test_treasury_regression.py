from __future__ import annotations

import threading

import pytest

from marginal import Action, AuthorizationRequired, BudgetLimits, Cost, Treasury
from marginal.policy import MarginalPolicy, PolicyConfig


def permissive_policy() -> MarginalPolicy:
    return MarginalPolicy(
        PolicyConfig(outcome_value_usd=10.0, minimum_roi=0.0, target_success_probability=1.0)
    )


def test_authorize_then_commit_consumes_budget_and_blocks_duplicate() -> None:
    treasury = Treasury(BudgetLimits(max_tokens=1_000), policy=permissive_policy())
    action = Action(name="search docs", kind="research", cost=Cost(tokens=100), expected_gain=0.1)
    assert treasury.authorize(action).allowed
    treasury.commit(action)
    assert treasury.usage.tokens == 100
    assert not treasury.authorize(action).allowed


def test_child_commit_is_charged_to_child_and_parent() -> None:
    parent = Treasury(BudgetLimits(max_tokens=1_000), policy=permissive_policy())
    child = parent.child("research", BudgetLimits(max_tokens=300))
    action = Action(name="first", kind="research", cost=Cost(tokens=200), expected_gain=0.1)
    assert child.authorize(action).allowed
    child.commit(action)
    assert child.usage.tokens == 200
    assert parent.usage.tokens == 200


def test_parallel_authorizations_cannot_oversubscribe_shared_budget() -> None:
    account = Treasury(BudgetLimits(max_tokens=100), policy=permissive_policy())
    barrier = threading.Barrier(3)
    decisions: list[bool] = []
    lock = threading.Lock()

    def authorize(action: Action) -> None:
        barrier.wait()
        result = account.authorize(action).allowed
        with lock:
            decisions.append(result)

    threads = [
        threading.Thread(
            target=authorize,
            args=(
                Action(
                    name="parallel 70",
                    kind="tool",
                    cost=Cost(tokens=70),
                    expected_gain=0.1,
                ),
            ),
        ),
        threading.Thread(
            target=authorize,
            args=(
                Action(
                    name="parallel 40",
                    kind="tool",
                    cost=Cost(tokens=40),
                    expected_gain=0.1,
                ),
            ),
        ),
    ]
    for thread in threads:
        thread.start()
    barrier.wait()
    for thread in threads:
        thread.join()
    assert sorted(decisions) == [False, True]


def test_sibling_cannot_settle_another_treasurys_action() -> None:
    root = Treasury(BudgetLimits(max_tokens=1_000), policy=permissive_policy())
    first = root.child("first", BudgetLimits(max_tokens=500))
    second = root.child("second", BudgetLimits(max_tokens=500))
    action = Action(name="owned", kind="tool", cost=Cost(tokens=100), expected_gain=0.1)
    assert first.authorize(action).allowed
    with pytest.raises(AuthorizationRequired):
        second.commit(action)
