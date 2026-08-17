# Measured public benchmark comparison

This report compares matched executions. It does not estimate or impute missing runs.
MARGINAL overhead is counted in net efficiency and net savings.

| Metric | Baseline | MARGINAL | Change |
|---|---:|---:|---:|
| Resolved | 0/3 | 0/3 | +0.00 pp |
| Agent tokens | 1,098,747 | 824,839 | 24.93% fewer |
| Effective tokens (incl. governance) | 1,098,747 | 824,839 | 24.93% fewer |
| Effective USD | n/a | n/a | n/a |
| Effective latency | 593,106 ms | 565,768 ms | 4.61% lower |
| Tool calls | 33 | 32 | 3.03% fewer |
| Repeated calls | 0 | 0 | 0.00% fewer |
| Tokens per resolved task | n/a | n/a | — |
| USD per resolved task | n/a | n/a | — |

## Governance tax

MARGINAL overhead: **0 tokens**, **n/a**, **7,058 ms**.
Gross agent-token savings: **24.93%**. Net token savings after governance: **24.93%**.

## Quality and intervention decision

Token uncertainty: **not evaluable** without a successful task in both arms.
Quality preserved within the 1.00 pp non-inferiority margin: **not evaluable**.
Regressions: **0**. Recoveries: **0**.
Reviewed deny recommendations: **0**. False stops: **0** (n/a).
Intervention status: **pass_through**.
No verified successful task was observed, so token efficiency per resolved task is undefined and the intervention cannot be classified as supported.

`pass_through` is a valid result: it means MARGINAL did not demonstrate enough net value to justify intervention under the preregistered threshold.
