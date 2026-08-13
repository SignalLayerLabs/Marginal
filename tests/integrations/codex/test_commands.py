from __future__ import annotations

import json
import subprocess
from pathlib import Path

from marginal.integrations.codex.commands import codex_command
from marginal.integrations.codex.evidence import EvidenceStore, summarize_evidence
from marginal.integrations.codex.identity import current_promotion_identity
from marginal.integrations.codex.promotion import enforcement_is_active


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True)


def _repository(path: Path) -> Path:
    path.mkdir()
    _git(path, "init", "-q")
    _git(path, "config", "user.email", "test@example.com")
    _git(path, "config", "user.name", "Test User")
    (path / "tracked.txt").write_text("initial\n", encoding="utf-8")
    _git(path, "add", "tracked.txt")
    _git(path, "commit", "-qm", "initial")
    return path


def test_status_defaults_to_shadow_without_receipt(tmp_path: Path, capsys) -> None:
    exit_code = codex_command("status", data_dir=tmp_path, as_json=True)

    payload = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert payload["mode"] == "shadow"
    assert payload["capability"] == "Tool Enforcement"


def test_unready_promotion_returns_two(tmp_path: Path, capsys) -> None:
    exit_code = codex_command("promote", data_dir=tmp_path, as_json=True)

    payload = json.loads(capsys.readouterr().out)
    assert exit_code == 2
    assert payload["error_code"] == "EVIDENCE_NOT_READY"


def test_demote_is_idempotent(tmp_path: Path, capsys) -> None:
    assert codex_command("demote", data_dir=tmp_path, as_json=True) == 0
    capsys.readouterr()
    assert codex_command("demote", data_dir=tmp_path, as_json=True) == 0
    assert json.loads(capsys.readouterr().out)["mode"] == "shadow"


def test_review_requires_explicit_candidate_verdict(tmp_path: Path, capsys) -> None:
    workspace = _repository(tmp_path / "repo")
    identity = current_promotion_identity(workspace)
    store = EvidenceStore(tmp_path / "data" / "evidence" / identity.repository_hash)
    store.append(
        {
            "schema_version": 1,
            "event": "decision",
            "session_hash": "session",
            "action_hash": "candidate",
            "semantic_key": "semantic",
            "state_hash": "state",
            "evidence_hash": "evidence",
            "reason_code": "NO_PROGRESS_RECOMMENDED_UNKNOWN",
            "latency_ms": 1.0,
            "covered": True,
            "coverable": True,
            "recommended_stop": True,
            "reviewed": False,
            "false_stop": False,
            "pending": False,
        }
    )

    exit_code = codex_command(
        "review",
        data_dir=tmp_path / "data",
        workspace=workspace,
        candidate="candidate",
        verdict="waste",
        as_json=True,
    )

    assert exit_code == 0
    assert json.loads(capsys.readouterr().out)["reviewed"] is True
    summary = summarize_evidence(store.read_all())
    assert summary.reviewed_candidates == 1
    assert summary.false_stops == 0


def test_ready_evidence_promotes_repository_with_live_receipt(tmp_path: Path, capsys) -> None:
    workspace = _repository(tmp_path / "repo")
    data = tmp_path / "data"
    identity = current_promotion_identity(workspace)
    store = EvidenceStore(data / "evidence" / identity.repository_hash)
    for index in range(100):
        store.append(
            {
                "schema_version": 1,
                "event": "decision",
                "session_hash": f"session-{index % 5}",
                "action_hash": f"action-{index}",
                "semantic_key": f"semantic-{index}",
                "state_hash": "state",
                "evidence_hash": "evidence",
                "outcome": "success",
                "reason_code": "NO_PROGRESS_OBSERVED" if index < 5 else "APPROVED",
                "latency_ms": 1.0,
                "covered": True,
                "coverable": True,
                "recommended_stop": index < 5,
                "reviewed": index < 5,
                "false_stop": False,
                "pending": False,
            }
        )
    for index in range(5):
        store.append(
            {
                "schema_version": 1,
                "event": "session_end",
                "session_hash": f"session-{index}",
            }
        )

    exit_code = codex_command(
        "promote",
        data_dir=data,
        workspace=workspace,
        as_json=True,
    )

    payload = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert payload["mode"] == "enforce"
    assert enforcement_is_active(data, identity=identity)
