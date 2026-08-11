# Smoke Failure Analysis

No trajectories are available yet. Observations and interpretations will be kept separate.

## Preflight blocker

- Observation: Codex 0.147 `PostToolUse` exposes shell output but not exit status. Treating
  every completed shell handler as successful would corrupt MARGINAL's successful-repeat
  history; treating every shell as failed makes the preregistered primary intervention
  effectively pass-through for searches and tests.
- Observation: task checkouts are materialized at the correct commits, but Codex is not
  yet executed inside the official pinned per-instance SWE-bench runtime.
- Observation: no official verifier backend is available on this host.
- Interpretation: executing trajectories now would measure an unfaithful mechanism in an
  uncontrolled task environment and would spend tokens without admissible correctness.
- Resolution: introduce a tested success-observable interception boundary, run Codex in
  the official task environment, configure the official verifier, and rerun full preflight.
