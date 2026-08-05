"""Wrap an OpenAI SDK call without adding an OpenAI dependency to MARGINAL."""

from marginal import (
    Action,
    BudgetLimits,
    Cost,
    Treasury,
    budgeted_call,
    extract_common_llm_usage,
)


def main() -> None:
    """Run the example after installing and configuring the optional OpenAI SDK."""

    from openai import OpenAI

    client = OpenAI()
    treasury = Treasury(BudgetLimits(max_tokens=50_000, max_usd=2.0))
    response = budgeted_call(
        treasury,
        client.responses.create,
        action=Action(
            name="draft answer",
            kind="llm",
            cost=Cost(tokens=4_000, usd=0.05),
            expected_gain=0.12,
        ),
        usage_extractor=extract_common_llm_usage,
        model="YOUR_MODEL",
        input="Explain marginal compute allocation.",
    )
    print(response)


if __name__ == "__main__":
    main()
