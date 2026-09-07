# SWE-bench Pro Container Lane Report

Implemented the minimal in-container Pro solver lane without running model inference or changing
the benchmark protocol.

## Delivered

- `benchmark/astra/pro_lane.py`: validates the instance ID, exact lowercase base commit, condition,
  fixed input paths, repository root, and non-existing output before mutation. It archives the base
  tree, retains ignored installed dependencies, removes future/current tracked content and original
  Git metadata, creates a deterministic detached single-commit snapshot, verifies tree equality and
  history size, rejects base trees containing gitlinks before mutation, purges nested Git metadata,
  forwards the unchanged public prompt to `run_task`, and records original/snapshot commit and tree
  hashes.
- `benchmark/astra/pro/Dockerfile.solver`: layers on a controller-supplied task image, uses pinned
  amd64 Alpine Node and uv builder manifests, installs Codex 0.153.4 with the existing wrapper,
  adds an independent musl Python 3.12.11 runtime, installs MARGINAL/benchmark packages into that
  runtime's site-packages, records source/task/tool labels, and invokes the lane CLI from `/app`.
- `.dockerignore`: admits only the Astra package files required by the solver image.
- `tests/benchmark/test_astra_pro_lane.py`: focused repository-isolation, validation, overwrite, and
  forwarding tests.

## Verification

```text
$ .venv/bin/python -m pytest -q tests/benchmark/test_astra_pro_lane.py
......                                                                   [100%]
7 passed in 2.24s
```

```text
$ .venv/bin/ruff check benchmark/astra/pro_lane.py tests/benchmark/test_astra_pro_lane.py
All checks passed!
```

The image build uses task image
`jefzda/sweap-images@sha256:d902632d1374cf0282a4ea301b82c296e13a41127308da0204aca87a4ba62c02`.
Despite earlier evaluator metadata describing Ubuntu 20.04/Python 3.8, this exact image is Alpine
Linux 3.18.3. The solver therefore uses musl-compatible Node and standalone Python binaries. Its
final image ID and no-inference executable smoke checks are recorded below once complete.

## Concerns

- Repository sanitization is intentionally destructive and is safe only because the official task
  container is disposable.
- Ignored dependency retention depends on the base tree's ignore rules. The verified snapshot tree
  contains only tracked base-commit files; ignored dependency content remains outside Git.
- Base commits containing gitlinks are rejected as unsupported infrastructure before mutation.
- No solver/model request was made during implementation or verification.
