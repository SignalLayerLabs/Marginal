# Benchmarking

## Demonstrations versus measured benchmarks

The Killer Demo and bundled synthetic benchmark test allocator behavior with declared costs. They do not measure a provider and are not universal savings claims.

## Required paired protocol

A real benchmark should keep constant:

- task and dataset version;
- model and provider version;
- system and user prompt;
- tools and permissions;
- repository state;
- time and token limits;
- verifier;
- task order and retry policy.

Compare baseline and MARGINAL on matched task IDs. Do not drop failures or impute missing runs. Benchmark rows are parsed strictly: boolean and numeric strings are rejected rather than coerced.

## Required metrics

- resolution rate and confidence interval;
- quality non-inferiority margin defined before results;
- uncached input, cached input, non-reasoning output, reasoning, and total tokens where available;
- direct cost and latency;
- tool and sub-agent calls;
- regressions and recoveries;
- cost per verified successful task;
- policy and estimator identities, including learned-state fingerprint;
- denied and recommended reason distribution;
- raw paired result files.


The bundled comparator exposes `--confidence-level`, `--quality-margin-pp`, `--bootstrap-samples`, and `--seed`. Record these values with the raw inputs. Its efficiency section reports tokens and USD per resolved task; a zero-resolved condition is reported as unavailable rather than divided by zero.

## Shadow evaluation

Shadow Mode is ideal for integration safety, estimator calibration, and false-denial analysis, but does not itself produce realized token savings because all actions still execute.

## Replay

Replay is useful for policy sensitivity analysis. It cannot model state changes from actions a different policy would have denied. Replay output must remain labeled estimated and non-causal. Malformed ledger authorization records are rejected.

## Causal evaluation

Causal marginal-value work requires an identification strategy, such as controlled randomization, paired trajectories, valid propensity logging, or another justified design. Historical success association alone is insufficient.
