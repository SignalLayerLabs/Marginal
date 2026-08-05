"""Rank candidate actions and reserve the best one."""

from marginal import (
    Action,
    BudgetLimits,
    Cost,
    MarginalPolicy,
    PolicyConfig,
    Treasury,
    funded_call,
)

policy = MarginalPolicy(
    PolicyConfig(
        outcome_value_usd=5.0,
        token_shadow_price_per_million_usd=10.0,
    )
)
treasury = Treasury(BudgetLimits(max_tokens=20_000, max_usd=1.0), policy=policy)

allocation = treasury.fund_best(
    [
        Action(
            name="ask another model",
            kind="review",
            cost=Cost(tokens=5_000, usd=0.08),
            expected_gain=0.03,
        ),
        Action(
            name="run targeted tests",
            kind="verification",
            cost=Cost(tokens=500, usd=0.001),
            expected_gain=0.18,
            is_verification=True,
        ),
    ]
)

if allocation is None:
    print("No candidate was worth funding.")
else:
    print(f"Funded: {allocation.action.name} ({allocation.decision.reason})")
    message = funded_call(treasury, allocation, lambda: "targeted tests passed")
    print(message)
