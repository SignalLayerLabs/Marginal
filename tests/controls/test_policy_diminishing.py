from __future__ import annotations

from marginal import (
    Action,
    BudgetLedger,
    BudgetLimits,
    Cost,
    DiminishingReturnConfig,
    DiminishingReturnDetector,
    MarginalPolicy,
)


def _retry(number: int) -> Action:
    return Action(
        name="verify README",
        kind="verification",
        cost=Cost(tokens=100),
        expected_gain=0.4,
        fingerprint=f"retry-{number}",
        metadata={
            "phase": "verify",
            "state_hash": "workspace-unchanged",
            "marginal_semantic_key": "verify:file:README.md",
        },
    )


def test_policy_can_discount_and_reject_repeated_same_state_work() -> None:
    policy = MarginalPolicy(
        diminishing_detector=DiminishingReturnDetector(
            DiminishingReturnConfig(gain_decay=0.5, max_same_state_repeats=2)
        )
    )
    ledger = BudgetLedger(BudgetLimits(max_tokens=10_000))

    first = policy.evaluate(_retry(1), ledger)
    assert first.allowed is True
    policy.observe_execution(_retry(1))

    second = policy.evaluate(_retry(2), ledger)
    assert second.allowed is True
    assert second.expected_gain == 0.2
    policy.observe_execution(_retry(2))

    third = policy.evaluate(_retry(3), ledger)
    assert third.allowed is False
    assert third.reason_code == "DIMINISHING_RETURN_REJECTED"
