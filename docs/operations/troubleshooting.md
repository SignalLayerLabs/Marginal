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
| `hook_state: not_observed`, `evidence_records: 0` | The plugin is installed but has never seen a session. | Run a Codex session in this repository. Nothing is wrong yet. |
| `mode: shadow`, `authority.effective: L0` | Shadow Mode. MARGINAL is recording and recommending only. | Nothing. This is the correct state until enforcement is earned. |
| `coverage_ratio` below `1.0`, `COVERAGE` in `next_promotion_blockers` | Some actions were not coverable by a hook. | Keep running sessions. Check `doctor` for `hooks_enabled: false`. |
| `authority.eligible: L0` with a non-empty `next_promotion_blockers` | Enforcement is not earned. | Clear the named blockers. Do not configure Enforce Mode to force it. |
| `stale_session_receipts` above `0`, or `ledger.valid: false` | Session receipts were left behind, or the governance ledger did not verify. | Read `ledger.error_codes` and `ledger.first_invalid_sequence`. |
| `doctor` → `blocking_reasons: ["CODEX_NOT_FOUND"]` | Codex CLI was not found. | Install Codex, then re-run `doctor`. `status` numbers are meaningless until this clears. |

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

`coverage_ratio` is `covered_actions / coverable_actions`. Below `1.0`, some
actions Codex took were not seen by a hook.

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

`stale_session_receipts` counts sessions that started and never cleanly
finished — usually a crashed or killed Codex process. They age out; a
persistent non-zero count means sessions are not terminating cleanly.

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

## Related

- [Codex plugin](../integrations/codex.md) — what the integration observes
  and controls
- [Integration overview](../integrations/overview.md#integration-labels) —
  Observe, Tool Enforcement, Full Compute Enforcement
- [Privacy](privacy.md) — what the Decision Ledger stores and what
  `ledger-export` shares
