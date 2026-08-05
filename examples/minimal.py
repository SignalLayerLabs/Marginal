"""Run with: python examples/minimal.py"""

from marginal import Action, BudgetLimits, Cost, MarginalPolicy, PolicyConfig, Treasury
from marginal.adapters import ActionDenied, budgeted_call

policy = MarginalPolicy(
    PolicyConfig(outcome_value_usd=5.0, token_shadow_price_per_million_usd=10.0)
)
treasury = Treasury(
    BudgetLimits(max_tokens=20_000, max_usd=1.00, verification_reserve_tokens=2_000),
    policy=policy,
)

def expensive_step(topic: str) -> str:
    return f"researched: {topic}"

try:
    result = budgeted_call(
        treasury,
        expensive_step,
        "agent economics",
        action=Action(
            name="research agent economics",
            kind="research",
            cost=Cost(tokens=2_000, usd=0.02),
            expected_gain=0.15,
        ),
    )
    print(result)
except ActionDenied as exc:
    print(f"skipped: {exc}")

print(treasury.summary())
