# Frequently asked questions

## Is MARGINAL a prompt compressor?

No. Prompt compressors reduce the size of a call. MARGINAL can decide not to make a
low-value call at all. The two approaches can be combined.

## Is MARGINAL a model router?

No. A router chooses a model. MARGINAL can evaluate multiple model calls as candidate
actions and fund the best one.

## Is this only a hard token budget?

No. Hard budgets are enforced, but the policy also compares expected success gain with
direct cost and configured shadow prices.

## Does MARGINAL estimate expected gain automatically?

The reference estimator supports explicit values, defaults, and transparent observed
averages by action kind. Causal estimation and counterfactual replay are future validation
work, not current claims.

## Does authorization consume budget?

It creates a reservation. Committed usage remains unchanged until settlement, but other
actions cannot spend the reserved capacity.

## What happens when a call fails?

The guarded sync and async wrappers abort and release the reservation, then re-raise the
original exception.

## What happens when actual usage exceeds the estimate?

The actual spend is recorded and traced, then `BudgetOverrun` is raised. Future decisions
see the real overrun.

## What happens when the trace sink fails?

An authorization trace failure rolls back the new reservation and approval counter. If a
guarded callable fails and abort tracing also fails, MARGINAL releases the reservation and
re-raises the callable's original exception with the trace error chained as its cause. After
external work succeeds, committed accounting is not rolled back if settlement tracing fails.

## Does MARGINAL store prompts?

Not by default. Automatic call fingerprints hash inputs and traces store the digest. Action
metadata is included in traces, so applications must not put secrets there.

## Is it thread-safe?

A root treasury and all its children share one re-entrant lock for authorization,
reservation, settlement, and abort operations. Reservations are owner-bound, and the JSONL
sink is thread-safe within one process.
