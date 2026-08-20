# Troubleshooting status and doctor

`marginal status` and `marginal doctor` answer two different questions.
`status` reports what MARGINAL has observed and what authority it currently
has. `doctor` reports whether the local Codex integration can observe anything
at all.

Read `doctor` first. If Codex is not reachable, every number in `status` is
zero for a reason that has nothing to do with your evidence.

Every identifier below is synthetic. Repository hashes are truncated to
`repo-alpha…` style placeholders; a real one is a 64-character hex digest.

## The matrix

| What you see | What it means | Next safe action |
| --- | --- | --- |
| `hook_state: not_observed`, `evidence_records: 0` | No hook event has ever arrived here. Expected on a fresh install — but identical to the plugin not being installed at all. | Run a Codex session in this repository, then look again. If it does not move, run `doctor`. |
| `mode: shadow`, `authority.effective: L0` | Shadow Mode. MARGINAL is recording and recommending only. | Nothing. This is the correct state until enforcement is earned. |
| `coverage_ratio` below `1.0`, `COVERAGE` in `next_promotion_blockers` | Of the decisions MARGINAL recorded, some were not covered. Says nothing about actions that never reached a hook. | Keep running sessions. Check `doctor` for `hooks_enabled: false`. |
| `authority.eligible: L0` with a non-empty `next_promotion_blockers` | Enforcement is not earned. | Clear the named blockers. Do not configure Enforce Mode to force it. |
| `stale_session_receipts` above `0`, or `ledger.valid: false` | Receipt files exist whose session did not answer, or the governance ledger did not verify. | Remove receipts you know are dead. For the ledger, read `ledger.error_codes` and `ledger.first_invalid_sequence`. |
| `doctor` → `blocking_reasons: ["CODEX_NOT_FOUND"]` | Codex CLI was not found *now*. No new activity can be observed until it is. | Install Codex, then re-run `doctor`. Evidence already on disk stays valid and `status` still reports it. |

## Plugin installed, no observed evidence

```
$ marginal status
mode: shadow
capability: Tool Enforcement
repository_hash: repo-alpha000000000000000000000000000000000000000000000000000000
hook_state: not_observed
hooks_observed: False
hooks_active: False
evidence_records: 0
covered_actions: 0
coverable_actions: 0
coverage_ratio: 0.0
```

`hook_state` has three values, and the difference matters:

- `not_observed` — no hook event has ever arrived.
- `observed` — events arrived previously, no session is live now.
- `active` — at least one session is live (`active_hook_sessions` above zero).

A fresh install sits at `not_observed`. That is not a fault. Run a Codex
session; if it stays `not_observed` afterwards, the hooks are not firing and
`doctor` is where to look.

What this state does **not** tell you is whether the plugin is installed.
`not_observed` with `evidence_records: 0` is the absence of evidence, and a
machine where the plugin was never installed prints exactly the same thing.
`doctor` is what distinguishes them — it probes the integration rather than
reading what the integration has already recorded.

`coverage_ratio: 0.0` here is the same kind of artefact. The ratio is
`covered_actions / coverable_actions`, and with a zero denominator it is
reported as `0.0` rather than left undefined. It means "nothing recorded", not
"nothing covered".

Note that `capability: Tool Enforcement` appears even here. It describes what
the Codex integration is *capable* of, not what is currently in force — that
is `authority.effective`.

## Shadow Mode is active

```
$ marginal status
mode: shadow
authority: {"ceiling": "L3", "configured_mode": "shadow", "current": "L0",
            "effective": "L0", "effective_blockers": [], "eligible": "L0"}
```

Shadow Mode records and recommends; it does not block. `effective: L0` is the
authority actually in force.

`effective_blockers` being empty does **not** mean enforcement is happening. It
means nothing is *blocking* the configured mode from taking effect — and the
configured mode is `shadow`. Read `configured_mode` and `effective` together.

## Incomplete hook coverage

```
$ marginal status
hook_state: active
active_hook_sessions: 1
covered_actions: 34
coverable_actions: 41
coverage_ratio: 0.8292682926829268
next_promotion_blockers: ["COVERAGE", "MINIMUM_REVIEWS"]
```

`coverage_ratio` is `covered_actions / coverable_actions`. Read what those two
numbers are counted over: both are sums across the decision records already in
the evidence store. Below `1.0` means *of the decisions MARGINAL recorded*,
some were marked coverable and not covered.

It is worth being exact about the limit, because the intuitive reading is
wrong. An action that never reached a hook produces no decision record, so it
lands in neither the numerator nor the denominator — it is invisible to this
ratio rather than counted against it. `coverage_ratio` therefore summarizes the
decision evidence MARGINAL observed. It is not a measure of total Codex runtime
coverage, and it cannot tell you what it never saw. A ratio of `1.0` is
consistent with complete coverage and equally consistent with a hook that
stopped firing.

Use it as a within-evidence quality signal, and use `doctor` for the separate
question of whether the integration can observe activity at all.

This is the concrete reason Codex is labelled Tool Enforcement rather than
Full Compute Enforcement: specialized and hosted tool paths can fall outside
local hook coverage. Partial coverage is expected, not necessarily a
misconfiguration. Treat a sudden drop as the signal, not a value below 1.

## Enforcement is not earned

```
$ marginal status
authority: {"ceiling": "L3", "configured_mode": "shadow", "current": "L0",
            "effective": "L0", "eligible": "L0"}
next_promotion_blockers: ["MINIMUM_ACTIONS", "MINIMUM_SESSIONS", "COVERAGE",
                          "MINIMUM_REVIEWS", "OUTCOME_UNOBSERVABLE",
                          "EVIDENCE_ROOT_UNVERIFIED"]
```

`eligible` is what the evidence would currently support; `ceiling` is the most
the configuration would ever allow. Promotion needs `eligible` to reach `L3`,
which needs `next_promotion_blockers` empty.

Each blocker is a separate requirement — clearing one does not shorten the
others. `OUTCOME_UNOBSERVABLE` and `EVIDENCE_ROOT_UNVERIFIED` in particular are
not about volume: the first means outcomes could not be classified, the second
that the evidence root did not verify.

There is no flag that skips this. That is the point of Earned Enforcement.

## Stale or drifted evidence

```
$ marginal status
stale_session_receipts: 3
ledger: {"error_codes": ["IO_ERROR"], "first_invalid_sequence": null,
         "records": 0, "root_hash": null, "valid": false}
permissions: {"evidence": "not_created", "governance_ledger": "not_created"}
```

Two different problems share this shape.

`stale_session_receipts` counts receipt files under `sessions/` whose session
did not answer when `status` asked it. Reachability is the whole test: the
receipt is read, and the session behind it is probed over loopback with a short
timeout. A receipt counts as stale if the file cannot be read, if it fails its
safety checks (a symlink, oversized, a non-loopback host, a token under 16
bytes), or if the probe does not come back `ok`.

There is **no time-based TTL**, so these do not age out on their own. A receipt
left by a crashed or killed Codex process stays counted until the file is
removed. A non-zero count means "these receipts point at nothing reachable
right now" — treat it as a prompt to clear dead receipts, not as something that
resolves by waiting.

Two consequences worth knowing: a session that is merely slow to answer within
the probe timeout is counted stale for that run, and the stale count is not
filtered by repository — unreachable receipts from any repository on this
machine are included, while `active_hook_sessions` counts only this one.

`ledger.valid: false` is more serious. Read the two fields next to it:
`first_invalid_sequence` names the record where verification failed, and a
`null` there with `records: 0` and `IO_ERROR` means the ledger could not be
read at all — usually it does not exist yet, which is normal before the first
session. A non-null `first_invalid_sequence` means the chain broke at a
specific record, and the evidence after it is not trustworthy.

When the ledger does not verify, `status` falls back to summarizing raw
records, so the counts stay populated while `EVIDENCE_ROOT_UNVERIFIED` blocks
promotion. Do not read populated counts as verified evidence.

## Codex is not reachable

```
$ marginal doctor
available: False
version:
hooks_enabled: False
plugins_enabled: False
capability_level: observe
capability_label: Observe
blocking_reasons: ["CODEX_NOT_FOUND"]
```

`doctor` reports `capability_label: Observe` when it cannot confirm control,
even though the Codex integration is Tool Enforcement when working. The label
degrades to what can be proven, not what is intended.

`effective_policy.effective: false` is the field that says enforcement is not
in force. When it is `false`, the runtime fails open: actions proceed. Nothing
in `status` should be read as blocking while that is the case.

`doctor` and `status` are answering different questions here, and this is the
state where the difference shows. `doctor` probes the integration now: can
MARGINAL observe new Codex activity? `CODEX_NOT_FOUND` answers no. `status`
reads evidence already persisted on disk for this repository, which is
unaffected — the counts, the ledger and the promotion blockers keep reporting
what was recorded before, and they remain valid.

So do not read `CODEX_NOT_FOUND` as invalidating `status`. Read it as: the
existing record still stands, and nothing will be added to it until Codex is
reachable again. The stale reading to guard against is treating an unchanging
`status` as evidence of a quiet period rather than of a broken integration.

## Related

- [Codex plugin](../integrations/codex.md) — what the integration observes
  and controls
- [Integration overview](../integrations/overview.md#integration-labels) —
  Observe, Tool Enforcement, Full Compute Enforcement
- [Privacy](privacy.md) — what the Decision Ledger stores and what
  `ledger-export` shares
