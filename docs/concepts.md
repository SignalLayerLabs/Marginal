# Concepts

## Action

An `Action` is a proposed unit of work. It has a stable name and kind, an estimated `Cost`,
an optional expected success gain, and caller-defined metadata.

## Cost

`Cost` normalizes four non-negative dimensions:

- token count;
- direct USD spend;
- latency in milliseconds;
- application-defined risk.

`PolicyConfig` converts them to a common value unit using optional shadow prices. Hard
budgets always inspect the original dimensions directly.

## Expected gain

Expected gain is the estimated increase in the probability of a verified successful
outcome. The policy caps it by the remaining distance to the configured success target, so
an action cannot claim more probability improvement than remains possible.

Applications may provide expected gain directly or use a `ValueEstimator`.

## Shadow price

A shadow price represents the opportunity cost of consuming a scarce resource. It is
separate from direct provider billing:

- `Cost.usd` is direct spend;
- `token_shadow_price_per_million_usd` prices scarce tokens;
- `latency_shadow_price_per_second_usd` prices waiting time;
- `risk_shadow_price_usd` prices the configured risk quantity.

## Treasury

A `Treasury` owns a policy, committed usage, pending reservations, duplicate state, and an
optional parent treasury. One root treasury should normally represent one task or workflow.

## Reservation

Approval reserves estimated resources immediately but does not add them to committed usage.
Reservations prevent parallel or sequential authorizations from promising the same budget
twice. Each reservation records its owning treasury, so siblings cannot settle or abort one
another's work. Reservations are converted to actual usage on `commit` or released on
`abort`.

## Verification reserve

Agents often spend an entire budget generating an answer and leave nothing for validation.
A verification reserve protects tokens or USD that only actions marked `is_verification`
may consume. A reserve requires the corresponding `max_tokens` or `max_usd` hard limit.
Verification already spent does not reduce the regular allocation unnecessarily.

## Allocation

`fund_best` evaluates a set of candidates against the same state and reserves the affordable
candidate with the highest marginal score. The returned `Allocation` contains the prepared
action and its explainable decision. Use `funded_call` or `async_funded_call` to execute and
settle it safely.

## Duplicate action

Direct treasury actions are fingerprinted from their declared action fields. Guarded
callables additionally include callable identity and arguments. MARGINAL performs exact,
deterministic deduplication; it does not claim semantic-similarity detection.

## Settlement and overrun

Settlement replaces a reservation with actual usage. If actual usage exceeds a limit, the
spend is still recorded because execution has already occurred, then `BudgetOverrun` is
raised. This preserves truthful accounting.

## Decision

Every `Decision` contains `allowed`, `reason`, `score`, `expected_gain`, and the estimated
cost value. Policies remain inspectable and auditable.
