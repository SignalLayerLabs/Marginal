# Research and prior art

MARGINAL is an implementation project, not a claim that marginal allocation was invented in
this repository.

## Primary research inspiration

Siqi Zhu, “Agentic AI Systems Should Be Designed as Marginal Token Allocators,” 2026:

- paper: <https://arxiv.org/abs/2605.01214>

The paper argues that routing, agent actions, serving, and training can be viewed through a
shared marginal-benefit and marginal-cost condition. MARGINAL implements a narrow runtime
slice that can work immediately with current Python agents and provider SDKs.

## Adjacent work

- AgentBudget: <https://agentbudget.dev/> — hard session budget enforcement and cost tracking;
- Budget-Aware Tool-Use / BATS: <https://arxiv.org/abs/2511.17006> — budget-aware tool-use and test-time scaling;
- OpenTelemetry GenAI conventions: <https://opentelemetry.io/docs/specs/semconv/gen-ai/> — interoperable observability signals.

These projects solve adjacent problems. MARGINAL focuses on online candidate valuation,
reservation, hierarchical accounting, and pre-execution selection.

## Evidence policy

The project distinguishes:

- functional tests proving specified behavior;
- synthetic benchmarks demonstrating mechanics;
- real workload evaluations measuring external validity.

Only the third category can support broad savings claims. Contributions that claim
performance improvements must include reproducible data and preserved-outcome metrics.
