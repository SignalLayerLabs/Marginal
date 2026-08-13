# FAQ

## Does MARGINAL guarantee fewer tokens on every request?

No. Some requests are already minimal, and some require additional verification. The target is lower avoidable compute per verified successful task across representative sessions.

## Does Shadow Mode save tokens?

No action is blocked in Shadow Mode. It creates the evidence needed to estimate which future enforcement decisions may be safe.

## Can Shadow Mode observe repeated concurrent actions?

Yes. Semantic duplicates are still recommended as duplicates, but non-blocking modes keep separate internal reservations so every execution is accounted without changing the agent's behavior.

## Is replay proof that denied actions were unnecessary?

No. Replay only reclassifies recorded proposed actions. It does not simulate the trajectory that would follow a denial.

## Does MARGINAL learn automatically from every successful task?

It records outcomes, but it does not assign causal credit automatically. Applications must provide defensible action-level realized gain or later use a validated estimator.

## How is estimator state versioned?

The estimator identity includes name, version, configuration hash, and training-data fingerprint. Online observations update the training-data fingerprint.

## What happens if a failed-call usage extractor also fails?

MARGINAL conservatively settles the reserved estimate, releases the reservation, and re-raises the original execution failure with the extraction error chained as its cause.

## Are Codex, Claude Code, Copilot, and OpenCode already supported?

Version `0.3.0` adds the native Codex reference plugin with local Tool Enforcement and Earned
Enforcement receipts. Claude Code, GitHub Copilot, and OpenCode remain roadmap milestones and are
not claimed complete.

## Does the protocol already generate modify, defer, reuse, stop, and force-verify actions?

The protocol defines those directives so adapters share one contract. The v0.3 reference policy
and runtime currently generate allow and deny. Richer automatic directives remain future policy
and adapter work.

## Does MARGINAL upload code or prompts?

The core has no mandatory network service and does not upload data. Prompts and outputs are not added automatically, but task IDs, action names, model identity, metadata, verifier details, error text, and exact timestamps can still be sensitive. Use `SAFE_TELEMETRY` to remove free text and pseudonymize identifiers, or `AGGREGATE_EXPORT` for grouped sharing. `LOCAL_FULL` preserves caller content. Pseudonymization is not anonymization.

## Where is the pseudonymization key stored?

Supply `privacy_key_path` explicitly or let a strict ledger create a hidden owner-only key beside the ledger. Keep the key outside version control and do not share an operational key with the dataset it protects. Existing group-readable or world-readable key files are rejected on POSIX systems.

## Is the Decision Ledger tamper-proof?

No. It is append-only at the application level, not cryptographically immutable. Use external signing or immutable storage when tamper evidence is required.
