# Community Feedback Log

MARGINAL is developed in public, but community feedback is treated as evidence to examine rather than instructions to implement automatically.

## Decision rule

A community criticism enters the product roadmap only when it identifies a reproducible user problem, a falsifiable product risk, a missing measurement, or a clearer way to explain an implemented capability. Unsupported claims about motives, universal model behavior, or performance are not promoted into product requirements.

## Review: model progress could make MARGINAL redundant

**Feedback:** a future model release may stop pathological verification loops, making MARGINAL unnecessary.

**Decision:** partially accepted; promoted into a product principle.

The criticism correctly attacks a weak version of the thesis. If MARGINAL were only a workaround for one model's repetitive behavior, it would have a short useful life. The durable problem is broader: users need an independent way to measure whether another unit of agent compute is expected to improve the verified outcome enough to justify its cost.

The criticism does **not** establish that model progress makes independent compute governance redundant. More capable models can still have different cost, latency, verification, tool-use and risk profiles. The value of the governor must therefore be measured per workload rather than assumed.

**Product consequence:** add Graceful Irrelevance. A configuration that does not demonstrate positive net intervention value should report `pass_through` instead of manufacturing an optimization claim.

## Review: endless verification loops

**Feedback:** repeated verification of an unchanged `.md` file is a current pain point.

**Decision:** accepted as a failure-mode example, rejected as a vendor/file-specific implementation target.

The useful abstraction is:

> same semantic action + unchanged observable state + no new evidence → diminishing expected marginal value.

**Product consequence:** add an opt-in state-aware `DiminishingReturnDetector`. It discounts repeated same-state work and can recommend a stop after a configured threshold. Missing state fails open; changed state or new evidence resets the repetition pressure.

## Review: providers may have incentives not to reduce waste

**Feedback:** longer runs generate more usage, so a provider may have little incentive to eliminate waste.

**Decision:** rejected as a product claim.

Usage-based pricing can create economic differences between provider and user objectives, but that does not establish intentional waste or deliberate preservation of loops. MARGINAL does not need to speculate about provider motives. The legitimate requirement is that users can observe and control their own compute economics independently of the provider.

**Communication consequence:** do not use claims such as “providers want agents to waste tokens.”

## Review: “less slop” in the website/post

**Feedback:** the website and launch copy feel too abstract.

**Decision:** partially accepted.

The technical concepts are not removed: transactional accounting, learning loop, privacy and the Universal Agent Protocol are implemented and remain important. The presentation order was the problem. The previous landing page asked a new visitor to understand the theory before seeing a concrete failure mode or the evidence needed to validate the product.

**Product communication consequence:** reorder the website to:

1. concrete trace;
2. proof standard;
3. net-value / governance-tax principle;
4. mechanism;
5. architecture and roadmap.

The new site labels its example as illustrative rather than benchmark evidence.

## Review: show SWE-bench Pro with MARGINAL OFF vs ON

**Feedback:** demonstrate value using the same coding benchmark with and without MARGINAL.

**Decision:** accepted in principle, with a methodological qualification.

Matched OFF/ON evaluation is exactly the right causal comparison for a runtime intervention. The same agent, model, prompt, tools, limits, task order and verifier should be held fixed. However, no single benchmark is treated as ground truth. Dataset version, task-quality exclusions, verifier behavior and known limitations must be recorded.

**Evidence consequence:** the benchmark report adds:

- effective tokens per verified successful task;
- gross versus net savings;
- governance tokens, USD and latency;
- repeated calls;
- regressions and recoveries;
- reviewed false stops;
- statistical uncertainty;
- an intervention status that can explicitly be `pass_through`.

The 10-task Codex canary remains an integration check. It must not be promoted into a general performance claim.

## What community influence means for MARGINAL

Community feedback is most valuable when it produces a harder falsification test. A good issue or comment does not need to agree with the project thesis. It should make the thesis more precise, measurable or easier to disprove.

The maintainers should publish negative benchmark results when a configuration does not meet the preregistered gate. That is part of the project's credibility, not a reason to hide the run.
