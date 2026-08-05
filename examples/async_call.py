"""Guard an asynchronous operation."""

import asyncio

from marginal import Action, BudgetLimits, Cost, MarginalPolicy, PolicyConfig, Treasury
from marginal.adapters import async_budgeted_call


async def research(topic: str) -> str:
    return f"researched: {topic}"


async def main() -> None:
    policy = MarginalPolicy(PolicyConfig(outcome_value_usd=5.0))
    treasury = Treasury(BudgetLimits(max_tokens=10_000), policy=policy)
    result = await async_budgeted_call(
        treasury,
        research,
        "agent economics",
        action=Action(
            name="research topic",
            kind="research",
            cost=Cost(tokens=1_000),
            expected_gain=0.10,
        ),
    )
    print(result)


if __name__ == "__main__":
    asyncio.run(main())
