# Changelog

All notable changes to MARGINAL are documented here. The project follows Semantic
Versioning.

## [0.1.0] - 2026-08-04

### Added

- provider-neutral `Action`, `Cost`, `Decision`, and `Allocation` value objects;
- deterministic `fund_best` candidate ranking and reservation;
- hard budgets for tokens, direct USD, latency, and risk;
- pending reservations that prevent concurrent and hierarchical oversubscription;
- protected verification reserves;
- marginal-value policy with token, latency, and risk shadow prices;
- expected-gain capping against the remaining success target;
- exact action and callable-input fingerprinting;
- duplicate prevention for pending and completed work;
- hierarchical treasuries with atomic child and parent accounting;
- explicit abort lifecycle and automatic release on callable failure;
- truthful settlement of actual usage with `BudgetOverrun` reporting;
- synchronous and asynchronous guarded-call and funded-allocation adapters;
- common OpenAI-, Anthropic-, and LiteLLM-like usage extraction;
- append-only JSONL traces and trace reporting CLI;
- transactional trace failure handling that preserves budget and primary-error semantics;
- deterministic synthetic benchmark and integration examples;
- end-to-end Killer Demo with a real generated code defect, verified baseline, action
  rankings, HTML/Markdown/SVG/JSON artifacts, one-command CLI execution, and a GitHub
  Pages deployment workflow;
- Python 3.10–3.13 CI, CodeQL, release automation, and community documentation.

### Limitations

- the bundled savings result is synthetic and is not a production performance claim;
- expected gains are caller-provided or based on transparent observed averages;
- causal value estimation and counterfactual replay are not included in this release.
