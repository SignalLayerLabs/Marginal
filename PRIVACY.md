# MARGINAL Privacy Notice

**Effective date:** 2026-08-13

MARGINAL is local-first open-source software. Commons is `local_only` by default for new and
existing Codex plugin installations, so the plugin makes no Commons network request unless the user
explicitly selects `read_only` or `contributor`.

## Data processed locally

Codex supplies lifecycle identifiers, tool names, tool inputs, tool responses, workspace paths,
and session metadata to local hooks. MARGINAL uses that input in memory to make a decision and to
derive hashes. By default it does not persist prompts, source code, raw commands, raw tool output,
transcripts, authentication files, or credential environment values.

The plugin may store redacted decisions, opaque hashes, aggregate coverage counts, outcome status,
reason codes, latency, review labels, promotion receipts, and user-private connection files under
Codex `PLUGIN_DATA`. Connection credentials are removed at session end. Local evidence remains
until the user deletes it or runs an explicit purge.

## Sharing and remote processing

`read_only` downloads a bounded, verified aggregate pack. `contributor` also sends a recursively
closed envelope containing an exact reviewed public-model namespace and bounded aggregate counts.
It excludes prompts, source, commands, outputs, paths, repository data, local hashes, timestamps,
free text, credentials, and persistent client or contributor identity. A one-time random retry
token is carried only in the `Idempotency-Key` HTTP header and is not part of the envelope or pack.

Contributor transport uses Cloudflare infrastructure. Cloudflare's handling of transport metadata,
including source IP addresses, is outside MARGINAL's application-level guarantees; MARGINAL makes
no anonymity claim. The application disables Worker observability and invocation logs and does not
persist request-derived metadata. Production contribution is not active until Wrangler
authentication and a dedicated least-privilege GitHub service credential are both verified.

Commons aggregates are model-specific priors only. They cannot affect local coverage, trust,
promotion, Autopilot, Decision Ledger identity, or Tool Enforcement. GitHub, Codex, Cloudflare,
package registries, and model providers remain governed by their own policies. Exporting a ledger
or attaching files to an issue is a separate explicit user action; inspect exports before sharing.

## User controls

- `$marginal` in Codex uses the bundled native control plane to show status or demote.
- `marginal install codex --commons-mode local_only|read_only|contributor` records an explicit
  Commons network posture when the optional Python package is installed.
- `codex plugin remove marginal@marginal` removes the plugin and preserves evidence.
- the optional Python package command `marginal uninstall codex --purge-data --yes` removes plugin
  data explicitly.

Security issues must follow [SECURITY.md](SECURITY.md). Privacy questions can be filed through the
private contact route described in [SUPPORT.md](SUPPORT.md).
