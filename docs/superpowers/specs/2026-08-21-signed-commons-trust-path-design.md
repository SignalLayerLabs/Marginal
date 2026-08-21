# Signed Commons Trust Path Design

## Purpose

Replace MARGINAL's hardcoded Commons `source_commit` trust pin with a rotatable signed release
chain. An offline Ed25519 root certifies an online release key, and the release key signs the exact
downloaded Commons pack bytes. A verified Commons pack remains a non-authoritative, model-specific
prior and cannot affect promotion, enforcement, thresholds, or local evidence.

## Runtime trust boundary

MARGINAL packages the closed public root-key object and frozen Commons schemas. Runtime code uses a
small stdlib-only Ed25519 verifier that enforces RFC 8032 verification rather than permissive
ZIP-215 behavior. It strictly decodes unpadded base64url, validates canonical point encodings,
rejects small-order and non-prime-subgroup points for both the public key and `R`, requires `S < L`,
and verifies `[S]B = R + [H(R || A || M)]A`.

The detached envelope has exactly the specified fields. Its certificate is canonicalized with
`sort_keys=True`, compact separators, `ensure_ascii=True`, and `allow_nan=False`, then verified by
the packaged root. The release key verifies the exact downloaded pack bytes. Only after those
checks pass does MARGINAL validate certificate revision bounds, the pack's internal canonical
SHA-256, its closed schema, lower-case 40-character provenance commit, and exact model registry.

## Network and cache

`CommonsClient.download()` performs two bounded fixed-path GET requests and returns
`CommonsPackDownload(pack: bytes, signature: bytes)`. Both requests retain the existing TLS,
resolution, monotonic-deadline, response-bound, and redacted-error behavior. No caller can select a
path.

The cache stores a single closed JSON object containing strict base64url encodings of the exact pack
and detached-envelope bytes. The existing descriptor-relative atomic replacement makes this one
transaction-safe artifact. Legacy unsigned pack files are never read as trusted input. A candidate
is accepted only after complete verification. A higher revision replaces the cache; an identical
artifact at the same revision succeeds idempotently; equivocation at the same revision and rollback
both fail while preserving the prior valid cache.

All download, signature, parsing, storage, and cache failures remain fail-open for local work.
Contributor mode continues processing its outbox after refresh failure.

## Trusted release builder

`scripts/build_commons_release.py` treats Marginal-Commons as untrusted structured Git data. It
resolves a commit, enumerates and reads only allowlisted release inputs with `git ls-tree` and
`git show`, rejects symlinks and non-regular entries, parses JSON with duplicate-key and recursion
bounds, and validates every object against MARGINAL's packaged contract. It never imports or
executes Commons code and never reads Commons `dist/`.

The revision is the count of commits in the selected commit's history that changed the allowlisted
aggregate/lifecycle inputs. The pack's `source_commit` is the newest commit affecting those inputs,
not arbitrary repository HEAD. Thus documentation-only commits reproduce identical signed content,
while an input change advances both provenance and revision. Aggregates are sorted and duplicate
dimensions are rejected, producing deterministic bytes.

The builder accepts the release seed only from `COMMONS_RELEASE_PRIVATE_KEY_B64URL`, strictly
decodes it, derives its public key with test/tooling-only `cryptography`, compares it with the frozen
release certificate, verifies that certificate against the packaged root using the independent
runtime verifier, and only then signs the exact final pack bytes. Secret values never enter output
or exception text.

## Release workflow and operations

The workflow runs only by dispatch or an approximately ten-minute schedule from trusted MARGINAL
`main`, with contents-read permission and the `commons-production` environment. It checks out
Marginal trusted code and full-history Marginal-Commons data separately, builds and independently
verifies the candidate, validates current production state, and deploys to the `marginal-commons`
Pages project with Wrangler 4.124.0 only when content changes. A missing production signature is
the one bootstrap exception. After bootstrap, invalid signed production state fails closed.

Operations documentation covers offline-root custody, online-key rotation, compromise response,
revocation limits, bootstrap, and the distinction between fail-open runtime consumption and
fail-closed publication. Signatures authenticate a release chain; they do not make aggregate data
authoritative or prove the correctness of upstream observations.

## Verification

Tests use RFC 8032 vectors and `cryptography`-generated fixtures rather than self-signing with the
runtime implementation. They cover strict Ed25519 rejection, closed envelope and pack parsing,
certificate bounds, cache rollback/equivocation/idempotence, exact-model isolation, fail-open sync,
immutable Git snapshot handling, poisoned Commons input, deterministic revision/content, signing-key
mismatch, workflow contract, package inclusion, and existing privacy/enforcement invariants.
