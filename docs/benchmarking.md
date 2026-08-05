# Benchmarking

## Killer demo

`marginal killer-demo --output killer-demo-output` runs an end-to-end coding workflow
against a generated buggy repository. It compares a run-everything baseline with MARGINAL's
funded action in each diagnose, fix, and verification stage. Both paths must pass the same
deterministic verifier. The generated HTML, Markdown, SVG, JSON, and JSONL trace make every
decision inspectable.

The committed result is available in [`demos/killer-demo`](../demos/killer-demo/RESULTS.md).
Its token, USD, and latency values are declared action-cost estimates used to exercise the
allocator; they are not provider telemetry.

It demonstrates the mechanism, but it is not a production benchmark or a claim that all
workloads will save 94.09%.

## Bundled synthetic benchmark

`marginal demo` runs five deterministic task scenarios. Each contains three actions needed
for a verified outcome and two low-value redundant actions. The baseline executes every
action. MARGINAL uses the reference policy and executes only actions that clear the economic
threshold.

The benchmark tests accounting, policy behavior, reserves, and reproducibility. It is not
evidence that every real agent will save the same percentage.

## Required production metrics

Real evaluations should report:

- task and verifier definition;
- model and provider versions;
- success rate with confidence intervals;
- input, output, cached, and reasoning tokens where available;
- direct cost and latency;
- tool and sub-agent calls;
- denied-action reasons;
- cost per verified successful outcome;
- quality difference against an uncontrolled baseline.

Savings without preserved quality are not optimization.

## Benchmark contribution rules

A contributed benchmark must be runnable, pinned to a dataset version, free from hidden
manual steps, and explicit about synthetic or simulated values. Raw result files should be
included or reproducibly generated.
