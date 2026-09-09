# Task 2 Implementer Report — Lite lane and solver image

## Delivered

- Added `benchmark.astra.lite_lane` with `LiteLaneConfig`, a `/testbed` default worktree,
  classic SWE-bench Lite ID validation, immutable run-directory protection, and fixed Astra
  Codex `RunConfig` values.
- The lane accepts the Task 1 `LiteTask` plus an absolute, isolated rendered `prompt_path`.
  It records the task identity, source `problem_hash`, exact-tree provenance, and SHA-256 of the
  rendered prompt. It deliberately does not compare that digest to `problem_hash`, because the
  latter is the raw problem-statement hash while the rendered prompt also contains the frozen
  template.
- Extracted Pro’s existing exact-tree recreation into internal
  `benchmark.astra._snapshot.prepare_exact_tree`. Pro passes `lane_name="Pro"`, preserving its
  snapshot author/committer identity, commit message, and one-commit result.
- Added `benchmark/astra/lite/Dockerfile.solver`: same pinned Codex 0.153.4, standalone
  CPython 3.12.11-musl, Node and uv builders as the Pro image; it derives from `TASK_IMAGE`,
  verifies the Lite module, sets `WORKDIR /testbed`, and invokes the Lite lane.

## Test-first evidence

RED:

```text
./.venv/bin/python -m pytest tests/benchmark/test_astra_lite_lane.py -q
ModuleNotFoundError: No module named 'benchmark.astra.lite_lane'
```

The initial `poetry run` attempt could not run because Poetry is not installed; the committed
worktree `.venv` was then used for every test/lint command.

GREEN:

```text
./.venv/bin/python -m pytest tests/benchmark/test_astra_lite_lane.py -q
3 passed in 1.64s

./.venv/bin/python -m pytest tests/benchmark/test_astra_pro_lane.py -q -k 'not manifest_instance_ids'
7 passed, 1 deselected in 1.96s

./.venv/bin/ruff check benchmark/astra/_snapshot.py benchmark/astra/lite_lane.py benchmark/astra/pro_lane.py tests/benchmark/test_astra_lite_lane.py
All checks passed!

./.venv/bin/ruff format --check benchmark/astra/_snapshot.py benchmark/astra/lite_lane.py benchmark/astra/pro_lane.py tests/benchmark/test_astra_lite_lane.py
4 files already formatted
```

The Lite tests cover classic ID acceptance; Pro-format and traversal rejection; original-tree
recreation with future history absent; and matched OFF/ON runner fields, with condition as the
only solver-condition difference. Existing Pro tests cover the extracted snapshot behavior.

## Image smoke limitation

Docker 29.5.2 is available and a local official Lite image was found. A no-provider build was
attempted with `swebench/sweb.eval.x86_64.pvlib_1776_pvlib-python-1072:latest`, but this execution
environment terminates child/background commands at its 30-second command boundary. The full
image build and subsequent no-provider exact-tree container smoke could therefore not be observed
to completion. No model inference was started.

The full existing Pro manifest-ID test likewise runs 731 separate repository validations and
exceeds that command boundary after the first seven tests; its focused non-manifest portion is
green above.

## Commit

Implementation commit: `c8f6324e8ae315e0d50d4da39581491e5a916489`
