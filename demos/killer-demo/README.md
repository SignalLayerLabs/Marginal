# Killer Demo artifacts

This directory contains the reproducible output of:

```bash
marginal killer-demo --output demos/killer-demo
```

Start with [RESULTS.md](RESULTS.md). Open `index.html` locally for the standalone visual
report. `result.json` contains the complete structured comparison and `trace.jsonl` contains
the provider-neutral candidate rankings, authorizations, and commits.

The fixture and workload are deterministic. Token, USD, and latency values are declared
action-cost estimates used to exercise the allocator, not provider telemetry. The result
demonstrates MARGINAL's allocation mechanism; it is not a production benchmark or a
universal savings claim.

A GitHub Pages workflow publishes this directory as a standalone site after Pages is set to
**GitHub Actions** in the repository settings.
