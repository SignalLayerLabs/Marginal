"""Wrap an Anthropic SDK call without adding an Anthropic dependency to MARGINAL."""

from marginal import (
    Action,
    BudgetLimits,
    Cost,
    Treasury,
    budgeted_call,
    extract_common_llm_usage,
)


def main() -> None:
    """Run the example after installing and configuring the optional Anthropic SDK."""

    import anthropic

    client = anthropic.Anthropic()
    treasury = Treasury(BudgetLimits(max_tokens=50_000, max_usd=2.0))
    response = budgeted_call(
        treasury,
        client.messages.create,
        action=Action(
            name="review answer",
            kind="llm",
            cost=Cost(tokens=3_000, usd=0.04),
            expected_gain=0.08,
        ),
        usage_extractor=extract_common_llm_usage,
        model="YOUR_MODEL",
        max_tokens=1_000,
        messages=[{"role": "user", "content": "Review this answer."}],
    )
    print(response)


if __name__ == "__main__":
    main()
