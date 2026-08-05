from __future__ import annotations

from marginal import Action, BudgetLimits, Cost, Treasury
from marginal.policy import MarginalPolicy, PolicyConfig


def permissive_policy() -> MarginalPolicy:
    return MarginalPolicy(
        PolicyConfig(
            outcome_value_usd=10.0,
            token_shadow_price_per_million_usd=0.0,
            minimum_roi=0.0,
            target_success_probability=1.0,
        )
    )


def test_authorize_then_commit_consumes_budget_and_blocks_duplicate() -> None:
    treasury = Treasury(BudgetLimits(max_tokens=1_000), policy=permissive_policy())
    action = Action(name="search docs", kind="research", cost=Cost(tokens=100), expected_gain=0.1)

    decision = treasury.authorize(action)
    assert decision.allowed
    assert treasury.usage.tokens == 0

    treasury.commit(action)
    assert treasury.usage.tokens == 100

    duplicate = treasury.authorize(action)
    assert not duplicate.allowed
    assert duplicate.reason == "rejected: duplicate action"


def test_child_commit_is_charged_to_child_and_parent() -> None:
    parent = Treasury(BudgetLimits(max_tokens=1_000), policy=permissive_policy())
    child = parent.child("research", BudgetLimits(max_tokens=300))
    first = Action(name="first", kind="research", cost=Cost(tokens=200), expected_gain=0.1)
    second = Action(name="second", kind="research", cost=Cost(tokens=150), expected_gain=0.1)

    assert child.authorize(first).allowed
    child.commit(first)

    assert child.usage.tokens == 200
    assert parent.usage.tokens == 200
    assert not child.authorize(second).allowed


def test_summary_accounts_for_approved_denied_and_committed_actions() -> None:
    treasury = Treasury(BudgetLimits(max_tokens=100), policy=permissive_policy())
    accepted = Action(name="small", kind="tool", cost=Cost(tokens=50), expected_gain=0.1)
    denied = Action(name="large", kind="tool", cost=Cost(tokens=101), expected_gain=0.1)

    treasury.authorize(accepted)
    treasury.commit(accepted)
    treasury.authorize(denied)

    summary = treasury.summary()

    assert summary["approved"] == 1
    assert summary["denied"] == 1
    assert summary["committed"] == 1
    assert summary["usage"]["tokens"] == 50


def test_changed_cost_estimate_does_not_bypass_duplicate_detection() -> None:
    account = Treasury(BudgetLimits(max_tokens=1_000), policy=permissive_policy())
    first = Action(
        name="same operation",
        kind="tool",
        cost=Cost(tokens=100),
        expected_gain=0.10,
        metadata={"target": "invoice-42"},
    )
    repriced = Action(
        name="same operation",
        kind="tool",
        cost=Cost(tokens=120),
        expected_gain=0.20,
        metadata={"target": "invoice-42"},
    )

    assert account.authorize(first).allowed
    account.commit(first)

    assert not account.authorize(repriced).allowed


def test_same_action_cannot_be_authorized_twice_while_pending() -> None:
    account = Treasury(BudgetLimits(max_tokens=1_000), policy=permissive_policy())
    action = Action(name="pending", kind="tool", cost=Cost(tokens=10), expected_gain=0.10)

    assert account.authorize(action).allowed
    second = account.authorize(action)

    assert not second.allowed
    assert second.reason == "rejected: duplicate pending action"


def test_pending_authorizations_cannot_oversubscribe_budget() -> None:
    account = Treasury(BudgetLimits(max_tokens=100), policy=permissive_policy())
    first = Action(name="first", kind="tool", cost=Cost(tokens=70), expected_gain=0.1)
    second = Action(name="second", kind="tool", cost=Cost(tokens=40), expected_gain=0.1)

    assert account.authorize(first).allowed
    denied = account.authorize(second)

    assert not denied.allowed
    assert denied.reason == "rejected: token budget exceeded"
    assert account.usage.tokens == 0


def test_child_pending_authorizations_reserve_parent_budget() -> None:
    parent = Treasury(BudgetLimits(max_tokens=100), policy=permissive_policy())
    first_child = parent.child("first", BudgetLimits(max_tokens=100))
    second_child = parent.child("second", BudgetLimits(max_tokens=100))
    first = Action(name="first", kind="tool", cost=Cost(tokens=70), expected_gain=0.1)
    second = Action(name="second", kind="tool", cost=Cost(tokens=40), expected_gain=0.1)

    assert first_child.authorize(first).allowed
    denied = second_child.authorize(second)

    assert not denied.allowed
    assert denied.reason == "rejected by parent: token budget exceeded"


def test_abort_releases_pending_authorization() -> None:
    account = Treasury(BudgetLimits(max_tokens=100), policy=permissive_policy())
    action = Action(name="retryable", kind="tool", cost=Cost(tokens=80), expected_gain=0.1)

    assert account.authorize(action).allowed
    account.abort(action, reason="operation failed")

    assert account.authorize(action).allowed
    assert account.summary()["aborted"] == 1


def test_explicit_fingerprint_allows_non_json_metadata() -> None:
    account = Treasury(BudgetLimits(max_tokens=100), policy=permissive_policy())
    action = Action(
        name="custom",
        kind="tool",
        cost=Cost(tokens=10),
        expected_gain=0.1,
        fingerprint="caller-controlled-id",
        metadata={"object": object()},
    )

    assert account.authorize(action).allowed


def test_fund_best_selects_highest_marginal_value_candidate() -> None:
    account = Treasury(
        BudgetLimits(max_tokens=1_000, max_usd=1.0),
        policy=MarginalPolicy(
            PolicyConfig(
                outcome_value_usd=1.0,
                token_shadow_price_per_million_usd=10.0,
                minimum_roi=0.0,
            )
        ),
    )
    low = Action(
        name="low",
        kind="research",
        cost=Cost(tokens=100, usd=0.01),
        expected_gain=0.05,
    )
    high = Action(
        name="high",
        kind="verification",
        cost=Cost(tokens=100, usd=0.01),
        expected_gain=0.20,
        is_verification=True,
    )

    allocation = account.fund_best([low, high])

    assert allocation is not None
    assert allocation.action.name == "high"
    assert allocation.decision.allowed
    assert account.ledger.reserved_usage.tokens == 100


def test_fund_best_returns_none_when_no_candidate_is_worth_funding() -> None:
    account = Treasury(
        BudgetLimits(max_usd=1.0),
        policy=MarginalPolicy(PolicyConfig(outcome_value_usd=1.0, minimum_roi=1.0)),
    )
    candidates = [
        Action(name="a", kind="tool", cost=Cost(usd=0.20), expected_gain=0.01),
        Action(name="b", kind="tool", cost=Cost(usd=0.30), expected_gain=0.02),
    ]

    assert account.fund_best(candidates) is None
    assert account.ledger.reserved_usage.usd == 0.0


def test_sibling_cannot_commit_another_treasurys_authorization() -> None:
    import pytest

    from marginal import AuthorizationRequired

    root = Treasury(BudgetLimits(max_tokens=1_000), policy=permissive_policy())
    first = root.child("first", BudgetLimits(max_tokens=500))
    second = root.child("second", BudgetLimits(max_tokens=500))
    action = Action(name="owned", kind="tool", cost=Cost(tokens=100), expected_gain=0.1)

    assert first.authorize(action).allowed

    with pytest.raises(AuthorizationRequired, match="authorized by this treasury"):
        second.commit(action)

    assert first.is_authorized(action)
    assert not second.is_authorized(action)


def test_sibling_cannot_abort_another_treasurys_authorization() -> None:
    import pytest

    from marginal import AuthorizationRequired

    root = Treasury(BudgetLimits(max_tokens=1_000), policy=permissive_policy())
    first = root.child("first", BudgetLimits(max_tokens=500))
    second = root.child("second", BudgetLimits(max_tokens=500))
    action = Action(name="owned abort", kind="tool", cost=Cost(tokens=100), expected_gain=0.1)

    assert first.authorize(action).allowed

    with pytest.raises(AuthorizationRequired, match="authorized by this treasury"):
        second.abort(action)

    assert first.is_authorized(action)


def test_parallel_authorizations_cannot_oversubscribe_shared_budget() -> None:
    import threading

    account = Treasury(BudgetLimits(max_tokens=100), policy=permissive_policy())
    barrier = threading.Barrier(3)
    decisions: list[bool] = []
    decisions_lock = threading.Lock()

    def authorize(action: Action) -> None:
        barrier.wait()
        allowed = account.authorize(action).allowed
        with decisions_lock:
            decisions.append(allowed)

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
    assert account.ledger.reserved_usage.tokens in {40, 70}


def test_trace_failure_rolls_back_authorization_reservation() -> None:
    import pytest

    class FailingTrace:
        def emit(self, event) -> None:
            del event
            raise OSError("trace unavailable")

    account = Treasury(
        BudgetLimits(max_tokens=100),
        policy=permissive_policy(),
        trace_sink=FailingTrace(),
    )
    action = Action(name="trace failure", kind="tool", cost=Cost(tokens=80), expected_gain=0.1)

    with pytest.raises(OSError, match="trace unavailable"):
        account.authorize(action)

    assert account.ledger.reserved_usage.tokens == 0
    assert not account.is_authorized(action)
    assert account.summary()["approved"] == 0
