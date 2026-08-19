# First contribution in 5 minutes

`CONTRIBUTING.md` describes the standards a change has to meet. This page is
the other half: where a small, low-risk change can start, and the shortest loop
that proves it works.

Nothing here relaxes those standards. The privacy, benchmark, and compatibility
requirements in [`CONTRIBUTING.md`](../../CONTRIBUTING.md) apply to a one-line
documentation fix exactly as they apply to a new adapter.

## Set up

```bash
git clone https://github.com/SignalLayerLabs/Marginal.git
cd Marginal
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
python -m pip install -e ".[dev]"
```

## Run one focused test

While iterating, run only the tests you are touching:

```bash
pytest tests/test_budget.py -q
```

A single file returns in about a second, which is what makes an edit-run loop
worth having. Narrow further with `-k`:

```bash
pytest tests/test_budget.py -q -k reservation
```

## Run the full checks before opening a pull request

```bash
ruff format --check src tests examples
ruff check src tests examples
mypy src/marginal
pytest -q
python -m build
python -m twine check dist/*
```

Run these before pushing, not after review. They are the same checks a reviewer
would otherwise run for you.

## Where a first change can safely start

### Documentation

The lowest-risk area, and the easiest place to be genuinely useful: a
definition that is stated in two places and has drifted, a step that no longer
matches the code, a missing link. Documentation must not broaden a capability
claim: the Observe / Tool Enforcement / Full Compute Enforcement labels in the
[integration overview](../integrations/overview.md#integration-labels) are the
ones to be most careful with.

### Synthetic fixtures

New test fixtures are welcome, with one hard rule.

**Examples and fixtures must use synthetic identifiers.** Never commit real
customer, repository, model, incident, or employee names as telemetry fixtures.
This is not a style preference -- fixtures end up in exports, and a real name in
a fixture is a privacy incident that outlives the pull request. Use obviously
invented values such as `repo-alpha`, `session-0001`, `user-a`.

### Examples

The scripts in `examples/` are executable and must stay runnable:

```bash
python examples/shadow_mode.py
python examples/universal_runtime.py
```

If you change a public API these exercise, run them. The same synthetic
identifier rule applies.

### Focused tests

Existing behavior that has no test is a good first contribution: it needs no
design decision, and it makes the next refactor safer.

Note the asymmetry in `CONTRIBUTING.md` -- *new behavior* requires a failing
test written **before** the implementation. Adding coverage for behavior that
already exists is the easier case, and the one to start with.

## What to expect in review

Pull requests should stay focused, and should explain the problem, interface,
behavior, validation, compatibility, privacy, and scientific limitations that
apply. Not every heading is relevant to every change -- a typo fix has no
scientific limitations -- but a reviewer should not have to ask which ones you
considered.
