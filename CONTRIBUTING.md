# Contributing to MARGINAL

Thank you for helping build open infrastructure for agent compute capital allocation.

## Principles

Contributions should preserve four properties:

1. decisions remain explainable;
2. denied actions never execute or consume budget;
3. benchmark claims remain reproducible and honestly labeled;
4. the core keeps zero mandatory runtime dependencies.

## Development setup

```bash
git clone https://github.com/SignalLayerLabs/Marginal.git
cd marginal
python -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[dev]"
```

On Windows, activate with `.venv\\Scripts\\activate`.

## Before opening a pull request

```bash
ruff format --check .
ruff check .
mypy src/marginal
pytest -q
python -m build
python -m twine check dist/*
```

New behavior requires a failing test before implementation. Add or update documentation for
public APIs and include a reproducible benchmark when making performance claims.

## Pull requests

Keep pull requests focused. Explain:

- the problem;
- the chosen design;
- user-visible behavior;
- validation performed;
- compatibility or security implications.

By contributing, you agree that your contribution is licensed under Apache-2.0.
