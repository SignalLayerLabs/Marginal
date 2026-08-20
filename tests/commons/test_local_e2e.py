from __future__ import annotations

import hashlib
import json
import subprocess
from dataclasses import replace
from pathlib import Path

import marginal.integrations.codex.service as service_module
from marginal.commons.client import CommonsAck
from marginal.commons.config import CommonsMode, configure_commons_mode
from marginal.commons.outbox import CommonsOutbox, OutboxEntry
from marginal.integrations.codex.events import SessionEvent
from marginal.integrations.codex.identity import current_promotion_identity
from marginal.integrations.codex.service import (
    read_mode,
    start_session_service,
    stop_session_service,
)
from marginal.integrations.codex.transport import request_session

_SOURCE_COMMIT = "7347a1b4024329780139d17494430f2ccac94fec"
_MODEL_NAMESPACES = (
    "openai/gpt-5.6-luna",
    "openai/gpt-5.6-sol",
    "openai/gpt-5.6-terra",
)


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True)


def _pack(models: dict[str, list[dict[str, object]]], *, revision: int) -> bytes:
    payload: dict[str, object] = {
        "schema_version": "1.0",
        "source_commit": _SOURCE_COMMIT,
        "commons_revision": revision,
        "compatibility": {"evidence_envelope_schema_version": "1.0"},
        "models": {
            namespace: {"aggregates": models.get(namespace, [])} for namespace in _MODEL_NAMESPACES
        },
    }
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    payload["integrity"] = {"sha256": hashlib.sha256(canonical).hexdigest()}
    return (json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n").encode()


class _LocalIngressCommonsAdapter:
    """Synthetic closed Ingress boundary backed by aggregate-only local Commons files."""

    def __init__(self, root: Path) -> None:
        self.root = root
        self.models: dict[str, list[dict[str, object]]] = {}
        self.revision = 1
        self.submitted_bodies: list[bytes] = []
        self.retry_headers: list[str] = []
        self._write_pack()

    def _write_pack(self) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        (self.root / "commons-pack-v1.json").write_bytes(_pack(self.models, revision=self.revision))

    def download(self) -> bytes:
        return (self.root / "commons-pack-v1.json").read_bytes()

    def submit(self, entry: OutboxEntry) -> CommonsAck:
        envelope = json.loads(entry.body_bytes)
        assert set(envelope) == {"schema_version", "model_namespace", "atoms"}
        assert entry.retry_token.encode() not in entry.body_bytes
        namespace = envelope["model_namespace"]
        aggregates = self.models.setdefault(namespace, [])
        for atom in envelope["atoms"]:
            aggregates.append({**atom, "lifecycle": "candidate"})
        self.submitted_bodies.append(entry.body_bytes)
        self.retry_headers.append(entry.retry_token)
        self.revision += 1
        self._write_pack()
        aggregate_path = self.root / namespace / "aggregates.json"
        aggregate_path.parent.mkdir(parents=True, exist_ok=True)
        aggregate_path.write_text(
            json.dumps({"aggregates": aggregates}, sort_keys=True, separators=(",", ":")) + "\n",
            encoding="utf-8",
        )
        return CommonsAck(accepted=True, duplicate=False)


def test_local_lifecycle_round_trip_is_model_isolated_private_and_non_authoritative(
    tmp_path: Path, monkeypatch
) -> None:
    """Catches uploads of raw context, cross-model priors, or Commons authority escalation."""

    canary = "MARGINAL-PRIVACY-CANARY-7f93"
    workspace = tmp_path / canary / "repository"
    workspace.mkdir(parents=True)
    _git(workspace, "init", "-q")
    _git(workspace, "config", "user.email", "test@example.com")
    _git(workspace, "config", "user.name", "Test User")
    tracked = workspace / f"{canary}.txt"
    tracked.write_text("private source\n", encoding="utf-8")
    _git(workspace, "add", tracked.name)
    _git(workspace, "commit", "-qm", "initial")

    data = tmp_path / "plugin-data"
    boundary = _LocalIngressCommonsAdapter(tmp_path / "local-boundary")
    configure_commons_mode(data, mode=CommonsMode.CONTRIBUTOR)
    monkeypatch.setattr(service_module, "_commons_client", lambda: boundary)
    start = SessionEvent(
        session_id="contributor-session",
        cwd=str(workspace),
        hook_event_name="SessionStart",
        model="gpt-5.6-sol",
        permission_mode="default",
        source="startup",
    )
    connection = start_session_service(start, data_root=data)
    for index in range(5):
        pre = {
            "session_id": start.session_id,
            "cwd": str(workspace),
            "model": start.model,
            "permission_mode": "default",
            "turn_id": canary,
            "tool_name": "Read",
            "tool_input": {"path": str(tracked)},
            "hook_event_name": "PreToolUse",
            "tool_use_id": f"{canary}-{index}",
        }
        assert request_session(connection, operation="pre", payload=pre)["ok"] is True
        assert (
            request_session(
                connection,
                operation="post",
                payload={
                    **pre,
                    "hook_event_name": "PostToolUse",
                    "tool_response": {"exit_code": 0},
                },
            )["ok"]
            is True
        )
    stop_session_service(start.session_id, data_root=data)

    assert len(boundary.submitted_bodies) == 1
    assert len(boundary.retry_headers) == 1
    assert CommonsOutbox(data).pending(limit=8).entries == ()
    assert canary.encode() not in boundary.submitted_bodies[0]
    persisted_boundary = b"".join(
        path.read_bytes() for path in boundary.root.rglob("*") if path.is_file()
    )
    assert canary.encode() not in persisted_boundary

    same_model = start_session_service(
        replace(start, session_id="same-model-session"), data_root=data
    )
    same_status = request_session(same_model, operation="status", payload={})["result"]
    stop_session_service("same-model-session", data_root=data)
    assert same_status["commons_prior_count"] == 1

    other_model = start_session_service(
        replace(start, session_id="other-model-session", model="gpt-5.6-terra"),
        data_root=data,
    )
    other_status = request_session(other_model, operation="status", payload={})["result"]
    stop_session_service("other-model-session", data_root=data)
    assert other_status["commons_prior_count"] == 0

    repository_hash = current_promotion_identity(workspace).repository_hash
    assert read_mode(data, repository_hash=repository_hash)["mode"] == "shadow"
