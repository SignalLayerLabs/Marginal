# Signed Commons release operations

MARGINAL Commons releases use an offline Ed25519 root to certify an online release key. MARGINAL
runtime distributions contain the root public key only. Each detached release envelope carries the
root-signed release certificate and a release-key signature over the exact pack bytes.

## Key custody and rotation

Keep the root private key offline and outside developer machines, CI, and repository storage. The
online release seed belongs only in the `commons-production` GitHub Environment as
`COMMONS_RELEASE_PRIVATE_KEY_B64URL`. Restrict that environment and the Cloudflare token to the
smallest practical maintainer and deployment scope.

To rotate the online key, create a new closed release certificate with a unique key ID and bounded
revision interval, sign its canonical JSON bytes offline with the root, review the three public
contract files, and update MARGINAL before using the new release seed. Overlap revision intervals
only when an intentional rollout needs it. Do not overwrite an existing key ID with different key
material.

If an online release key may be compromised, remove it from the production environment, stop the
release workflow, and ship a MARGINAL update whose trusted policy no longer accepts its certificate
before resuming publication with a newly certified key. Revision bounds limit where a certificate
is accepted but are not a network revocation mechanism. A root-key compromise requires a new root
anchor and a MARGINAL software update; signatures already trusted by old clients cannot be remotely
revoked.

## Publication behavior

The scheduled and manually dispatched workflow runs only from `SignalLayerLabs/Marginal` `main` in
the protected `commons-production` environment. It checks out Marginal-Commons with full history as
data, reads immutable Git objects, never imports or executes Commons code, builds a deterministic
candidate, and verifies it with both the runtime verifier and `cryptography` before comparison.
The official checkout and Python setup actions are pinned to immutable commits. The signing job
installs only exact-version binary release dependencies accepted by the reviewed SHA-256 lock file;
the private seed is exposed only to the candidate-build step and must never be logged or persisted.

The first signed deployment may replace the existing unsigned production pack when the signature
path is absent and the complete paginated Cloudflare deployment history contains no earlier signed
release. This is the one bootstrap exception. Once any signed production deployment exists, a
missing, malformed,
rollback, or same-revision-conflicting production artifact makes publication fail closed. Wrangler
is pinned to 4.124.0 and deploys only a verified candidate containing the two fixed `dist/` paths.

Runtime consumption has the opposite availability posture: network, signature, schema, and cache
failures return no shared prior and never block local work or Contributor outbox processing. A
signed Commons pack authenticates its release chain and bytes; it does not prove that upstream
observations are correct.

## Authority boundary

Commons remains a non-authoritative prior. Its signatures and lifecycle labels cannot activate
Tool Enforcement, promote Autopilot, change thresholds, override local evidence, or grant any local
authority. Local Only remains the default, sharing still requires explicit Contributor mode, and
Sol, Terra, and Luna priors remain isolated by exact canonical namespace.
