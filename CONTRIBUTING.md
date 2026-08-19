# Contributing to MARGINAL

Thank you for helping build open infrastructure for economically disciplined AI agents.

New here? [First contribution in 5 minutes](docs/project/first-contribution.md) shows where a small,
low-risk change can start and the shortest loop that validates it. The standards below still apply.

## Principles

Contributions must preserve these properties:

1. decisions remain explainable and versioned;
2. Enforce Mode never executes denied actions;
3. Shadow and Recommend modes never silently change caller behavior;
4. actual spend is recorded truthfully, including failed calls;
5. task outcomes are not misrepresented as causal action value;
6. benchmark claims are reproducible and honestly labeled;
7. prompts, outputs, credentials, and proprietary code are not logged by default;
8. the core keeps zero mandatory runtime dependencies.

## Development setup

```bash
git clone https://github.com/SignalLayerLabs/Marginal.git
cd Marginal
python -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[dev]"
```

On Windows, activate with `.venv\Scripts\activate`.

## Before opening a pull request

```bash
ruff format --check src tests examples
ruff check src tests examples
mypy src/marginal
pytest -q
python -m build
python -m twine check dist/*
```

Run the executable examples when changing their public APIs:

```bash
python examples/shadow_mode.py
python examples/universal_runtime.py
```

New behavior requires a failing test before implementation. Public API changes require documentation, compatibility notes, and schema updates when applicable. Changes to protocol or ledger serialization must add strict round-trip tests and validate the matching JSON schemas. Privacy changes must test representative quasi-identifiers, unknown fields, key handling, and the absence of free text from strict exports.

## Adapter contributions

An adapter must:

- use the Universal Agent Protocol rather than duplicate policy logic;
- publish its capabilities honestly;
- preserve action IDs and lifecycle correlation;
- distinguish supported directives from protocol extension points;
- settle actual usage or explicitly report that usage is unavailable;
- document fail-open and fail-closed behavior;
- include protocol conformance and end-to-end tests;
- avoid logging prompts or source code by default.

An adapter must not advertise Full Compute Enforcement unless the underlying engine exposes official controls for the relevant model turns, tool calls, retry loops, and stopping behavior.

## Estimator contributions

An estimator must expose a stable name, semantic version, configuration hash, training-data fingerprint when applicable, and provenance. It must report uncertainty or explicitly state that uncertainty is unavailable. Claims of causal marginal value require an identification strategy, not only historical correlation.

## Ledger and replay contributions

Ledger changes must preserve required envelope fields, monotonic process-local sequencing, strict parsing, and task/outcome correlation. Document any concurrency guarantees explicitly. Replay changes must remain labeled as off-policy diagnostics unless they implement and validate a defensible causal method.

## Privacy contributions

Privacy-sensitive changes must preserve the separation between the operational ledger and shareable exports. Contributors must:

- classify every newly persisted field as safe by default, pseudonymous, or potentially sensitive;
- default unknown fields to potentially sensitive;
- keep `safe_telemetry` allowlist-based rather than blocklist-based;
- avoid adding free-form strings, model identity, metadata, tool arguments, or exception text to strict telemetry;
- use field-separated keyed pseudonyms for correlation identifiers;
- keep pseudonymization keys outside traces, examples, fixtures, and version control;
- update both root and packaged JSON Schemas when an export contract changes;
- document whether a change affects local ledgers, safe event-level telemetry, aggregate exports, or all three;
- state explicitly when a technique is pseudonymization rather than anonymization.

Tests and examples must use synthetic identifiers. Never commit real customer, repository, model, incident, or employee names as telemetry fixtures.

## Pull requests

Keep pull requests focused. Explain the problem, interface, behavior, validation, compatibility, privacy, and scientific limitations. By contributing, you agree that your contribution is licensed under Apache-2.0.
