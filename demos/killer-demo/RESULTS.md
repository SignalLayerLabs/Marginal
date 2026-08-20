# MARGINAL Demo 001

**AI agents repeat work that changed nothing. MARGINAL catches it.**

Observe first. Prove waste. Earn enforcement.

> Deterministic functional demonstration using declared action-cost estimates; not provider telemetry, not a production benchmark, and not a claim about every agent workload.

This deterministic artifact demonstrates MARGINAL's compute-selection discipline. The no-progress repetition sequence shown in the HTML is an explicitly labeled runtime-pattern illustration, not provider telemetry and not an enforcement benchmark.

Scenario: **Fix a percentage-discount bug in a deterministic Python repository**

![Without MARGINAL versus MARGINAL](comparison.svg)

## Deterministic allocation proof

```diff
- return total - rate
+ return total * (1 - rate)
```

Verifier: `apply_discount(100.0, 0.20) == 80.0`

Initial verifier: **FAIL**

| Metric | Without MARGINAL | MARGINAL | Observed demo delta |
|---|---:|---:|---:|
| Declared tokens | 72,800 | 4,300 | **94.09%** |
| Calls | 9 | 3 | **66.67%** |
| Estimated USD | $0.763 | $0.026 | **96.59%** |
| Estimated latency | 22,030 ms | 1,230 ms | **94.42%** |
| Verified outcome | PASS | PASS | preserved |

## Allocation decisions

### Diagnose

Selected: **inspect the failing assertion** — approved: marginal ROI 7.166

Declared cost: **1,200 tokens · $0.006**. Alternatives rejected: **2**.

### Fix

Selected: **apply the targeted one-line patch** — approved: marginal ROI 7.418

Declared cost: **2,400 tokens · $0.018**. Alternatives rejected: **2**.

### Verify

Selected: **run the targeted verifier** — approved: marginal ROI 21.394

Declared cost: **700 tokens · $0.002**. Alternatives rejected: **2**.

## What this demo proves

- The deterministic task starts in FAIL and both workflows finish in PASS.
- The allocator can reject higher-cost actions while preserving the verifier outcome.
- Costs are declared demo estimates, not provider billing or production telemetry.
- The artifact is a mechanism demonstration, not a production benchmark.

## Reproduce

```bash
marginal killer-demo --output killer-demo-output
```
