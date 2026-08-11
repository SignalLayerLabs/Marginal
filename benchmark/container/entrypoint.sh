#!/bin/bash
set -Eeuo pipefail

umask 077

required=(
  MARGINAL_INSTANCE_ID
  MARGINAL_CONDITION
  MARGINAL_EXPECTED_BASE_COMMIT
  MARGINAL_MODEL
  MARGINAL_REASONING_EFFORT
  MARGINAL_TIMEOUT_SECONDS
)
for name in "${required[@]}"; do
  if [[ -z "${!name:-}" ]]; then
    echo "missing required environment: ${name}" >&2
    exit 64
  fi
done
if [[ "${MARGINAL_CONDITION}" != "baseline" && "${MARGINAL_CONDITION}" != "marginal" ]]; then
  echo "invalid MARGINAL_CONDITION" >&2
  exit 64
fi

mkdir -p /marginal-home/codex /marginal-home/home
install -m 0600 /run/secrets/codex-auth.json /marginal-home/codex/auth.json
export CODEX_HOME=/marginal-home/codex
export HOME=/marginal-home/home
export PYTHONPATH=/opt/marginal/src:/opt/marginal
export MARGINAL_SOCKET=/marginal-run/marginal.sock
export MARGINAL_HOOK_FAILURE_LOG=/marginal-run/hook-failures.log

if ! git -C /testbed cat-file -e "${MARGINAL_EXPECTED_BASE_COMMIT}^{commit}"; then
  echo "expected base commit is absent from task image" >&2
  exit 65
fi
git -C /testbed checkout --detach --force "${MARGINAL_EXPECTED_BASE_COMMIT}"
git -C /testbed reset --hard "${MARGINAL_EXPECTED_BASE_COMMIT}"
git -C /testbed clean -ffd
if [[ "$(git -C /testbed rev-parse HEAD)" != "${MARGINAL_EXPECTED_BASE_COMMIT}" ]]; then
  echo "task checkout did not reach expected base commit" >&2
  exit 65
fi
if [[ -n "$(git -C /testbed status --porcelain --untracked-files=all)" ]]; then
  echo "task checkout is not clean" >&2
  exit 65
fi

source /opt/miniconda3/etc/profile.d/conda.sh
conda activate testbed

daemon_pid=""
cleanup() {
  if [[ -n "${daemon_pid}" ]] && kill -0 "${daemon_pid}" 2>/dev/null; then
    kill -TERM "${daemon_pid}" 2>/dev/null || true
    wait "${daemon_pid}" 2>/dev/null || true
  fi
}
trap cleanup EXIT TERM INT

if [[ "${MARGINAL_CONDITION}" == "marginal" ]]; then
  /usr/bin/python3 -m benchmark.codex_adapter.daemon \
    --socket "${MARGINAL_SOCKET}" \
    --events /marginal-run/treasury-events.jsonl \
    --summary /marginal-run/daemon-summary.json \
    > /marginal-run/daemon.stdout.log \
    2> /marginal-run/daemon.stderr.log &
  daemon_pid=$!

  ready=0
  for _ in $(seq 1 200); do
    if [[ -S "${MARGINAL_SOCKET}" ]]; then
      ready=1
      break
    fi
    if ! kill -0 "${daemon_pid}" 2>/dev/null; then
      break
    fi
    sleep 0.05
  done
  if [[ "${ready}" != "1" ]]; then
    echo "MARGINAL daemon did not become ready" >&2
    exit 70
  fi

  /usr/bin/python3 -c \
    'from benchmark.codex_adapter.hook_config import install_project_hooks; install_project_hooks("/testbed", python_executable="/usr/bin/python3", hook_client="/opt/marginal/benchmark/codex_adapter/hook_client.py")'
fi

shell_policy="$(/usr/bin/python3 -c 'import json, os; values={"HOME":"/marginal-home/home","LANG":"C.UTF-8","LC_ALL":"C.UTF-8","PATH":os.environ["PATH"],"TERM":"dumb"}; print("{" + ",".join(f"{key}={json.dumps(value)}" for key, value in sorted(values.items())) + "}")')"

command=(
  /opt/marginal-tools/bin/codex exec
  --ignore-user-config
  --ignore-rules
  --ephemeral
  --json
  --color never
  --strict-config
  --dangerously-bypass-hook-trust
  --enable codex_hooks
  -m "${MARGINAL_MODEL}"
  -c "model_reasoning_effort=\"${MARGINAL_REASONING_EFFORT}\""
  -c 'approval_policy="never"'
  -c 'sandbox_workspace_write.network_access=false'
  -c 'shell_environment_policy.inherit="none"'
  -c 'shell_environment_policy.ignore_default_excludes=false'
  -c "shell_environment_policy.set=${shell_policy}"
  -s workspace-write
  -C /testbed
)
disabled_features=(
  apps
  browser_use
  browser_use_external
  browser_use_full_cdp_access
  computer_use
  goals
  image_generation
  in_app_browser
  multi_agent
  multi_agent_v2
  plugins
  search_tool
  skill_search
  standalone_web_search
  tool_suggest
  web_search_request
  workspace_dependencies
)
for feature in "${disabled_features[@]}"; do
  command+=(--disable "${feature}")
done
command+=(-)

set +e
timeout --signal=TERM --kill-after=30s "${MARGINAL_TIMEOUT_SECONDS}s" \
  "${command[@]}" \
  < /marginal-run/prompt.txt \
  > /marginal-run/codex-events.jsonl \
  2> /marginal-run/codex-stderr.log
codex_status=$?
set -e

git -C /testbed diff --binary HEAD -- . ':(exclude).codex' > /marginal-run/model.patch
git -C /testbed diff --numstat HEAD -- . ':(exclude).codex' > /marginal-run/model.numstat
git -C /testbed status --porcelain --untracked-files=all -- . ':(exclude).codex' \
  > /marginal-run/worktree.status
printf '{"codex_exit_code":%d,"condition":"%s","instance_id":"%s"}\n' \
  "${codex_status}" "${MARGINAL_CONDITION}" "${MARGINAL_INSTANCE_ID}" \
  > /marginal-run/container-status.json

if [[ -n "${daemon_pid}" ]]; then
  kill -TERM "${daemon_pid}" 2>/dev/null || true
  wait "${daemon_pid}" || true
  daemon_pid=""
fi

exit "${codex_status}"
