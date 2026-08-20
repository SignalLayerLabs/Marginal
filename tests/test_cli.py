from __future__ import annotations

import json

from marginal.cli import main
from marginal.integrations.codex.installer import CodexInstallation


def write_trace(path) -> None:
    events = [
        {
            "event": "authorization",
            "decision": {"allowed": True},
            "action": {"name": "research"},
            "usage": {"tokens": 0, "usd": 0.0, "latency_ms": 0, "risk": 0.0},
        },
        {
            "event": "commit",
            "action": {"name": "research"},
            "usage": {"tokens": 120, "usd": 0.03, "latency_ms": 200, "risk": 0.0},
        },
    ]
    path.write_text("\n".join(json.dumps(event) for event in events) + "\n")


def test_report_command_renders_human_summary(tmp_path, capsys) -> None:
    trace = tmp_path / "trace.jsonl"
    write_trace(trace)

    exit_code = main(["report", str(trace)])

    output = capsys.readouterr().out
    assert exit_code == 0
    assert "Committed actions: 1" in output
    assert "Tokens: 120" in output
    assert "USD: $0.030000" in output


def test_report_command_supports_json(tmp_path, capsys) -> None:
    trace = tmp_path / "trace.jsonl"
    write_trace(trace)

    exit_code = main(["report", str(trace), "--json"])

    payload = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert payload["committed"] == 1
    assert payload["usage"]["tokens"] == 120


def test_validate_rejects_invalid_jsonl(tmp_path, capsys) -> None:
    trace = tmp_path / "bad.jsonl"
    trace.write_text('{"event":"commit"}\nnot-json\n')

    exit_code = main(["validate", str(trace)])

    assert exit_code == 1
    assert "line 2" in capsys.readouterr().err


def test_demo_matches_committed_benchmark(capsys) -> None:
    from marginal.benchmark import render_markdown, run_benchmark

    exit_code = main(["demo"])

    assert exit_code == 0
    assert capsys.readouterr().out == render_markdown(run_benchmark())


def test_codex_status_dispatches_without_importing_at_cli_module_load(tmp_path, capsys) -> None:
    exit_code = main(["codex", "status", "--data-dir", str(tmp_path), "--json"])

    assert exit_code == 0
    assert json.loads(capsys.readouterr().out)["mode"] == "shadow"


def test_install_cli_persists_only_an_explicit_closed_commons_choice(
    tmp_path, capsys, monkeypatch
) -> None:
    captured = {}

    def fake_install(**kwargs):
        captured.update(kwargs)
        return CodexInstallation(True, True, commons_mode="contributor")

    monkeypatch.setattr("marginal.integrations.codex.installer.install", fake_install)

    assert (
        main(
            [
                "install",
                "codex",
                "--data-dir",
                str(tmp_path),
                "--commons-mode",
                "contributor",
                "--json",
            ]
        )
        == 0
    )
    assert captured["commons_mode"] == "contributor"
    assert json.loads(capsys.readouterr().out)["commons_mode"] == "contributor"
