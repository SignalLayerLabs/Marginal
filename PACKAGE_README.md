# MARGINAL Community Hardening Overlay

This ZIP is a repository overlay prepared for `SignalLayerLabs/Marginal` `main` at commit `d6ab5c745f1a2ec19b2cb2395a1e6bfae66f2de5`.

## What it contains

- model-independent diminishing-return control;
- governance-tax and explicit false-stop accounting;
- net-value public benchmark reporting and CLI gates;
- evidence-first README / GitHub Pages rewrite;
- community feedback decision log;
- Codex benchmark-readiness specification;
- documentation reorganization tooling;
- focused tests and validators.

## Important

This package does **not** contain a completed Codex adapter and does not contain benchmark results. It prepares the evidence/control layer for v0.3.

The Visual Studio upload prompt is intentionally distributed separately and must not be committed.

## Apply order

1. Start from a clean checkout of `SignalLayerLabs/Marginal` `main`.
2. Extract this ZIP over the repository root, replacing matching files.
3. Run `python scripts/reorganize_docs.py` once.
4. Review `MIGRATION_MANIFEST.json` and the resulting `git diff`.
5. Run the focused validators and the full repository quality gate described in the external Visual Studio prompt.
6. Commit the source changes only; do not commit this ZIP or the external prompt.
