#!/bin/sh
set -eu

CODEX_PACKAGE_ROOT="${CODEX_PACKAGE_ROOT:-/opt/marginal-tools/lib/codex}"
CODEX_NATIVE_ROOT="${CODEX_PACKAGE_ROOT}/node_modules/@openai/codex-linux-x64/vendor/x86_64-unknown-linux-musl"

PATH="${CODEX_NATIVE_ROOT}/codex-path:${PATH}"
export PATH
export CODEX_MANAGED_PACKAGE_ROOT="${CODEX_PACKAGE_ROOT}"
unset CODEX_MANAGED_BY_NPM CODEX_MANAGED_BY_BUN CODEX_MANAGED_BY_PNPM CODEX_MANAGED_BY_VITE_PLUS
export CODEX_MANAGED_BY_NPM=1

exec "${CODEX_NATIVE_ROOT}/bin/codex" "$@"
