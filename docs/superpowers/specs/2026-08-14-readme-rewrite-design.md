# MARGINAL README rewrite design

## Goal

Make the README understandable to a new Codex user in one pass. Lead with the product, installation,
and safety contract. Keep evidence claims precise and move implementation detail to linked docs.

## Target structure

1. Hero and one-sentence product definition.
2. `What MARGINAL does` in four concrete bullets.
3. Codex install and uninstall commands.
4. `How Autopilot works`: Shadow Mode, evidence, earned authority, recovery.
5. Natural-language controls and diagnostic commands.
6. Explicit enforcement boundary: constrained local reads only; generic shell, tests, search,
   writes, network, deploy, and unknown MCP actions remain non-enforcing.
7. Privacy and integrity guarantees.
8. Evidence table with the historical 3-task smoke and an explicit non-causal warning.
9. Python-library quickstart, architecture, documentation, contributing, and license.

## Editorial rules

- Target 180--220 lines.
- Use short paragraphs and concrete nouns.
- One installation section; no duplicated commands.
- No community-response narrative in the landing page.
- No unsupported token-saving, causal, or full-compute-enforcement claims.
- Do not call configured authority effective authority without verified receipts and ledger state.
- Prefer links over inline implementation explanations.
- Preserve important compatibility, privacy, benchmark, and removal instructions.

## Non-goals

- No code, policy, runtime, benchmark, or release behavior changes.
- No new product promises.
- No rewriting linked technical documents in this change.

## Verification

- All internal README links resolve to repository files.
- Install, uninstall, status, doctor, explain, and privacy commands match the CLI/plugin surface.
- Runtime claims match the current enforcement allowlist and evidence gates.
- `ruff format --check README.md` and repository documentation checks pass.
- Final diff is reviewed for duplicated concepts, vague adjectives, and unsupported claims.
