# Quickstart

## Install

```bash
pip install "marginal-ai @ git+https://github.com/SignalLayerLabs/Marginal.git@v0.1.0"
```

MARGINAL supports Python 3.10–3.13 and has no mandatory runtime dependencies.

## Guard one action

```python
from marginal import (
    Action,
    ActionDenied,
    BudgetLimits,
    Cost,
    MarginalPolicy,
    PolicyConfig,
    Treasury,
    budgeted_call,
    funded_call,
)

policy = MarginalPolicy(
    PolicyConfig(
        outcome_value_usd=10.0,
        token_shadow_price_per_million_usd=12.0,
        minimum_roi=1.25,
        target_success_probability=0.95,
    )
)

treasury = Treasury(
    BudgetLimits(
        max_tokens=25_000,
        max_usd=1.00,
        verification_reserve_tokens=3_000,
    ),
    policy=policy,
)

try:
    result = budgeted_call(
        treasury,
        expensive_operation,
        "authentication",
        action=Action(
            name="inspect documentation",
            kind="research",
            cost=Cost(tokens=2_000, usd=0.02),
            expected_gain=0.10,
        ),
    )
except ActionDenied as exc:
    result = None
    print(exc.decision.reason)
```

A denial happens before `expensive_operation` is called. An approval reserves the estimate
until it is committed or aborted.

## Choose among candidates

```python
allocation = treasury.fund_best(
    [
        Action(
            name="ask another model",
            kind="review",
            cost=Cost(tokens=5_000, usd=0.08),
            expected_gain=0.03,
        ),
        Action(
            name="run tests",
            kind="verification",
            cost=Cost(tokens=500, usd=0.001),
            expected_gain=0.16,
            is_verification=True,
        ),
    ]
)

if allocation is not None:
    result = funded_call(treasury, allocation, execute, allocation.action)
```

## Configure economic assumptions

```python
from marginal import MarginalPolicy, PolicyConfig

policy = MarginalPolicy(
    PolicyConfig(
        outcome_value_usd=10.0,
        token_shadow_price_per_million_usd=12.0,
        latency_shadow_price_per_second_usd=0.002,
        risk_shadow_price_usd=2.0,
        minimum_roi=1.25,
        minimum_expected_gain=0.01,
        target_success_probability=0.95,
    )
)
```

`outcome_value_usd` is the application-defined value of moving a task from zero to certain
success. Shadow prices express the opportunity cost of scarce tokens, latency, and risk.
`Cost.usd` remains the direct estimated or measured spend used by hard USD budgets.

## Record actual provider usage

```python
from marginal import extract_common_llm_usage

response = budgeted_call(
    treasury,
    client.responses.create,
    action=action,
    usage_extractor=extract_common_llm_usage,
    model="YOUR_MODEL",
    input="Analyze the evidence.",
)
```

A custom extractor uses this contract:

```python
def extract_usage(result, estimated_cost):
    return Cost(
        tokens=result.usage.total_tokens,
        usd=estimated_cost.usd,
        latency_ms=estimated_cost.latency_ms,
        risk=estimated_cost.risk,
    )
```

## Persist evidence

```python
from marginal import JsonlTraceSink

trace = JsonlTraceSink("run.jsonl")
treasury = Treasury(BudgetLimits(max_tokens=25_000), trace_sink=trace)
```

```bash
marginal validate run.jsonl
marginal report run.jsonl
```
