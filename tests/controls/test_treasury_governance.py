from __future__ import annotations

import pytest

from marginal import Action, BudgetLimits, Cost, Treasury


def test_shadow_mode_can_review_a_false_stop_without_inferring_it() -> None:
    treasury = Treasury(
        BudgetLimits(max_tokens=10_000, max_usd=10.0),
        mode="shadow",
    )
    action = Action(
        name="expensive review",
        kind="review",
        cost=Cost(tokens=100, usd=1.0),
        expected_gain=0.0,
        fingerprint="review-1",
    )

    decision = treasury.authorize(action)
    assert decision.allowed is True
    assert decision.recommended is False
    treasury.commit(action)
    treasury.record_stop_review(action, would_have_helped=True)

    governance = treasury.summary()["governance"]
    assert governance["reviewed_stops"] == 1
    assert governance["false_stops"] == 1
    assert governance["false_stop_rate"] == 1.0


def test_stop_review_rejects_actions_that_were_not_denied() -> None:
    treasury = Treasury(BudgetLimits(max_tokens=10_000), mode="shadow")
    action = Action(
        name="free useful action",
        kind="verification",
        expected_gain=0.5,
        fingerprint="useful-1",
    )
    treasury.authorize(action)

    with pytest.raises(ValueError, match="not previously recommended"):
        treasury.record_stop_review(action, would_have_helped=False)
