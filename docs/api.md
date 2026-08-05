# API reference

## `Cost`

```python
Cost(tokens=0, usd=0.0, latency_ms=0, risk=0.0)
```

All values must be finite and non-negative. Token and latency counters must be integers.

## `Action`

```python
Action(
    name="run tests",
    kind="verification",
    cost=Cost(tokens=500),
    expected_gain=0.15,
    current_success_probability=0.70,
    is_verification=True,
    fingerprint=None,
    metadata={"suite": "unit"},
)
```

Expected gain and current probability are bounded between zero and one.

## `PolicyConfig`

```python
PolicyConfig(
    outcome_value_usd=1.0,
    token_shadow_price_per_million_usd=0.0,
    latency_shadow_price_per_second_usd=0.0,
    risk_shadow_price_usd=1.0,
    minimum_roi=1.0,
    minimum_expected_gain=0.0,
    target_success_probability=1.0,
)
```

## `BudgetLimits`

```python
BudgetLimits(
    max_tokens=None,
    max_usd=None,
    max_latency_ms=None,
    max_risk=None,
    verification_reserve_tokens=0,
    verification_reserve_usd=0.0,
)
```

A non-zero verification reserve requires the corresponding token or USD maximum.

## `Treasury`

Primary methods:

- `authorize(action) -> Decision`;
- `propose(action) -> Decision` alias;
- `fund_best(actions) -> Allocation | None`;
- `is_authorized(action) -> bool`;
- `commit(action) -> BudgetUsage`;
- `abort(action, reason=...) -> None`;
- `child(name, limits) -> Treasury`;
- `summary() -> dict`.

## Exceptions

- `ActionDenied`: wrapper refused execution;
- `AuthorizationRequired`: commit or abort without approval;
- `BudgetExceeded`: direct ledger operation exceeded a hard limit;
- `BudgetOverrun`: actual settled usage exceeded its reservation or hard limit.

## Usage extractors

```python
def extractor(result: object, estimated_cost: Cost) -> Cost:
    ...
```

The extractor must return the complete actual or best-known cost.

## Execution helpers

- `budgeted_call`: authorize, execute, and settle one synchronous callable;
- `async_budgeted_call`: asynchronous equivalent;
- `funded_call`: execute and settle an `Allocation` reserved by `fund_best`;
- `async_funded_call`: asynchronous funded-allocation equivalent.

## Killer demo

```python
from marginal import run_killer_demo

result = run_killer_demo("killer-demo-output")
```

The function returns the complete structured result and optionally writes Markdown, HTML,
SVG, JSON, and JSONL trace artifacts.
