# Measured public benchmark comparison

This report compares matched executions. It does not estimate or impute missing runs.
MARGINAL overhead is counted in net efficiency and net savings.

| Metric | Baseline | MARGINAL | Change |
|---|---:|---:|---:|
| Resolved | 0/3 | 0/3 | +0.00 pp |
| Agent tokens | 1,098,747 | 824,839 | 24.93% fewer |
| Effective tokens (incl. governance) | 1,098,747 | 824,839 | 24.93% fewer |
| Effective USD | $0.0000 | $0.0000 | 0.00% lower |
| Effective latency | 593,106 ms | 565,768 ms | 4.61% lower |
| Tool calls | 33 | 32 | 3.03% fewer |
| Repeated calls | 0 | 0 | 0.00% fewer |
| Tokens per resolved task | n/a | n/a | — |
| USD per resolved task | n/a | n/a | — |

## Governance tax

MARGINAL overhead: **0 tokens**, **$0.000000**, **7,058 ms**.
Gross agent-token savings: **24.93%**. Net token savings after governance: **24.93%**.

## Quality and intervention decision

Net token savings 95.0% bootstrap interval: **21.52% to 28.07%**.
Quality preserved within the 1.00 pp non-inferiority margin: **True**.
Regressions: **0**. Recoveries: **0**.
Reviewed deny recommendations: **0**. False stops: **0** (n/a).
Intervention status: **pass_through**.
No verified successful task was observed, so token efficiency per resolved task is undefined and the intervention cannot be classified as supported.

`pass_through` is a valid result: it means MARGINAL did not demonstrate enough net value to justify intervention under the preregistered threshold.

## Scope and interpretation

This is an **exploratory 3-task smoke with one paired run per task**, not a population estimate or headline performance claim. Codex CLI 0.147.0 and GPT-5.6-sol ran under identical prompts, limits, task order, official task images and base commits. MARGINAL added 7,058 ms of measured local governance latency, zero external governance tokens and zero governance USD.

The token interval above is only a bootstrap over three task pairs; it cannot estimate run-to-run model variance because there was one repetition. All three observed ON trajectories had zero applied denies. The token difference therefore cannot be attributed to a stop decision, and neither lane's 0/3 resolve rate permits an efficiency-per-success claim.

## Verification chain

- Authoritative correctness: SWE-bench 4.1.0 Docker harness, x86_64, official pinned task images; 3/3 completed and 0 infrastructure errors in each lane.
- Cloud audit: [GitHub Actions + Modal run 31474500980](https://github.com/SignalLayerLabs/Marginal/actions/runs/31474500980); 2/3 completed and the same Modal image-build error occurred for `pylint-dev__astroid-1978` in both lanes. The cloud error is retained but excluded from scoring.
- Evidence: [`evidence/smoke-2026-08-11-dbce533/`](evidence/smoke-2026-08-11-dbce533/) contains predictions, telemetry, verifier reports, merged rows, provenance and raw public-evaluator output.
- Frozen task-set SHA-256: `1c8c06935484fd57f4c27c363418884542bcfb06c69d02f480b61fe7687b58eb`.
- MARGINAL source commit used by the runtime overlays: `dbce533e5c8e8def62b0543853d07cfab2bc79c1`.

The next promotion gate is a preregistered repeated canary with verified successes and enough repetitions to measure trajectory variance. Until then, `pass_through` is the evidence-backed product decision.
