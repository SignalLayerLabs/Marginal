# MARGINAL Community Evidence Hardening — Design

**Date:** 2026-08-07

## Objective

Convert the first substantive community criticisms into stronger, falsifiable product behavior without turning MARGINAL into a patch for one model release or accepting unsupported narratives.

## Design decisions

### 1. Model independence

Do not implement a GPT-5.6 or Markdown-specific loop detector. The reusable signal is semantic repetition under unchanged state without new evidence.

### 2. Conservative diminishing-return control

Add an opt-in `DiminishingReturnDetector` under `src/marginal/controls/`. It evaluates without mutation and observes history only after successful execution. Missing state fails open. Changed state/evidence resets repetition pressure.

The detector may discount expected gain before the normal ROI decision and may eventually recommend denial. It is not enabled by default in the reference policy until representative engine telemetry validates thresholds.

### 3. MARGINAL self-accounting

Add `GovernanceTracker` to count:

- policy decision latency;
- externally introduced governance tokens/USD/latency;
- reviewed deny recommendations;
- explicit false stops.

Parent/child treasuries share a tracker so a hierarchy reports one governance-tax surface.

### 4. False stops are labels, not inferred causality

A task result cannot establish that an individual blocked action would or would not have helped. `Treasury.record_stop_review(...)` therefore requires an explicit external boolean label and only accepts actions previously recommended for denial.

### 5. Net-value public evaluation

Extend `RunRecord` additively. Existing v0.2 JSONL rows remain valid. Public evaluation reports workload-only gross savings and effective net savings after governance overhead.

The legacy `savings` key remains available and points to the net result. For old rows with zero governance overhead the numerical behavior is unchanged.

### 6. Graceful Irrelevance

The evaluator can return:

- `supported`;
- `pass_through`;
- `quality_regression`;
- `false_stop_risk`.

`pass_through` is a valid result when quality is preserved but net token savings do not clear the preregistered threshold.

### 7. Evidence-first website

The product website should no longer lead with architecture abstractions. Narrative order:

1. illustrative failure trace, explicitly not a benchmark;
2. proof standard;
3. governance tax and Graceful Irrelevance;
4. generic diminishing-return mechanism;
5. community decision log;
6. benchmark discipline;
7. roadmap.

No fabricated token-savings number is used.

### 8. Community governance

Create a durable Community Feedback Log. Feedback can be accepted, partially accepted or rejected with rationale. Unsupported claims about provider intent are rejected; valid falsification tests are promoted into roadmap/evidence requirements.

### 9. Documentation information architecture

Keep Python core modules stable except for a new `controls` package. Reorganize documentation by user intent:

```text
docs/
  getting-started/
  product/
  integrations/
  evaluation/
  reference/
  operations/
  project/
  superpowers/
```

Use `git mv` through a deterministic migration script and rewrite relative Markdown links.

### 10. Codex boundary

This hardening package prepares v0.3 but does not implement or claim a Codex adapter. The next implementation must use the official integration surface available at that time, default to Shadow Mode, capture measured telemetry, and target one-command installation.

## Compatibility constraints

- Python 3.10–3.13.
- Zero mandatory runtime dependencies.
- Existing v0.1/v0.2 constructor call sites remain valid.
- Existing public benchmark JSONL rows remain valid.
- Existing synthetic demo remains labeled synthetic.
- No provider-specific logic enters the decision core.
- No performance claim is added without measured data.
