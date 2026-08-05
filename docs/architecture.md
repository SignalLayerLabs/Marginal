# Architecture

MARGINAL separates description, ranking, reservation, execution, and settlement.

```text
Candidate actions
    │
    ├─► hard child and parent budgets
    ├─► pending reservations
    ├─► duplicate and stopping checks
    ├─► ValueEstimator.estimate
    └─► MarginalPolicy.evaluate
              │
       rank by marginal score
              │
       reserve best candidate
              │
       execute callable
          ┌───┴────┐
       success   failure
          │          │
     settle actual  abort
          │          │
       committed   released
          └────┬─────┘
          append trace
```

## Modules

- `models.py`: immutable provider-neutral values;
- `budget.py`: hard constraints, reservations, settlement, and accounting;
- `estimator.py`: transparent expected-gain estimates;
- `policy.py`: economic scoring and explanations;
- `fingerprint.py`: deterministic action and call identity;
- `treasury.py`: lifecycle, ranking, hierarchy, and atomic coordination;
- `adapters.py`: guarded sync and async Python or SDK calls;
- `trace.py`: append-only JSONL evidence;
- `cli.py`: trace validation, reporting, and demonstration;
- `benchmark.py`: deterministic synthetic scenarios.

## Authorization lifecycle

`authorize` evaluates an action and reserves its estimated cost across the child ledger and
every ancestor. The root and its children share one re-entrant lock, preventing concurrent
fan-out from oversubscribing a parent budget. Pending fingerprints also retain their owning
treasury, preventing cross-sibling settlement or cancellation.

Committed usage remains separate from reserved usage. `Treasury.summary()` exposes both.

## Settlement lifecycle

`commit` replaces every reservation in the hierarchy with actual usage. All levels are
updated consistently. If actual usage exceeds one or more limits, a `BudgetOverrun` is
raised only after the spend is recorded and traced.

`abort` releases every reservation without recording spend. The sync and async wrappers call
it automatically when the guarded callable raises.

Trace writes participate in the authorization transaction: a failed authorization trace rolls
back reservations and counters. Abort releases state before tracing; if tracing also fails, the
guarded callable's original exception is re-raised with the trace failure chained as its cause.
Settlement remains fail-truthful: once external work has occurred, accounting is never rolled
back merely because a trace sink fails.

## Candidate ranking

`fund_best` evaluates all supplied candidates under the same locked state. Allowed candidates
are ordered by:

1. marginal score;
2. capped expected gain;
3. lower estimated cost value;
4. deterministic fingerprint tie-break.

Only the selected candidate is reserved. The full candidate evaluation is emitted as a
`candidate_ranking` trace event.

## Extension boundaries

Applications can replace the estimator or policy without changing actions, budgets,
wrappers, or traces. Framework adapters should translate native events into `Action` and
`Cost` rather than adding provider logic to the core.
