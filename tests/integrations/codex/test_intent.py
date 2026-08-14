from __future__ import annotations

import os
from pathlib import Path

import pytest

from marginal.integrations.codex.events import PreToolUseEvent
from marginal.integrations.codex.intent import (
    UserIntent,
    is_control_plane_action,
    normalize_user_prompt,
)


@pytest.mark.parametrize(
    ("prompt", "expected"),
    [
        ("  RUN\u3000IT AGAIN ", UserIntent(repeat_requested=True)),
        ("Rifai l'azione", UserIntent(repeat_requested=True)),
        ("esegui di nuovo", UserIntent(repeat_requested=True)),
        ("Procedi comunque", UserIntent(force_run=True)),
        ("Force the run", UserIntent(force_run=True)),
        ("Esegui comunque", UserIntent(force_run=True)),
        ("Metti in pausa MARGINAL", UserIntent(pause_marginal=True)),
        ("Riattiva marginal", UserIntent(resume_marginal=True)),
        ("Mostra lo stato di Marginal", UserIntent(status_requested=True)),
    ],
)
def test_user_intent_normalizes_italian_english_and_unicode(
    prompt: str, expected: UserIntent
) -> None:
    assert normalize_user_prompt(prompt) == expected


@pytest.mark.parametrize(
    "prompt",
    [
        "Pause Marginal, then resume Marginal",
        "Do not force run",
        "Do not repeat the command",
        "Don't pause Marginal",
        "Don't proceed anyway",
        "Do not execute anyway",
        "Non ripetere il comando",
        "Non sospendere Marginal",
        "Non procedere comunque",
        "Non eseguire comunque",
        "Continue with the investigation",
    ],
)
def test_user_intent_fails_open_for_ambiguous_or_negated_language(prompt: str) -> None:
    assert normalize_user_prompt(prompt) == UserIntent()


def _event(command: str) -> PreToolUseEvent:
    return PreToolUseEvent(
        session_id="session-1",
        cwd="/workspace",
        hook_event_name="PreToolUse",
        model="gpt-5.6-sol",
        permission_mode="default",
        turn_id="turn-1",
        tool_name="Bash",
        tool_use_id="call-1",
        tool_input={"command": command},
    )


def _trusted_plugin(root: Path) -> Path:
    script = root / "scripts" / "marginal_control.py"
    script.parent.mkdir(parents=True)
    (root / ".codex-plugin").mkdir()
    (root / ".codex-plugin" / "plugin.json").write_text("{}", encoding="utf-8")
    script.write_text("#!/usr/bin/env python3\n", encoding="utf-8")
    return script


def test_control_plane_accepts_only_exact_trusted_script_and_subcommand(tmp_path: Path) -> None:
    trusted = tmp_path / "installed" / "marginal"
    script = _trusted_plugin(trusted)

    assert is_control_plane_action(
        _event(f"python3 {script} status --workspace /workspace --json"), trusted
    )
    candidate = "a" * 64
    assert is_control_plane_action(
        _event(
            f'py -3 "{script}" review --workspace "/workspace with spaces" '
            f"--candidate {candidate} --verdict waste --json"
        ),
        trusted,
    )
    assert not is_control_plane_action(_event(f"python3 {script} purge"), trusted)


@pytest.mark.parametrize(
    "suffix",
    [
        "status --data-dir /tmp/lookalike",
        "status --workspace",
        "status --unknown value",
        "doctor --workspace /workspace",
        "review --candidate abc",
        "review --candidate abc --verdict unknown",
        "promote positional-argument",
    ],
)
def test_control_plane_rejects_arguments_outside_the_exact_command_contract(
    tmp_path: Path, suffix: str
) -> None:
    trusted = tmp_path / "installed" / "marginal"
    script = _trusted_plugin(trusted)

    assert not is_control_plane_action(_event(f"python3 {script} {suffix}"), trusted)


def test_control_plane_rejects_lookalike_traversal_symlink_and_shell_injection(
    tmp_path: Path,
) -> None:
    trusted = tmp_path / "installed" / "marginal"
    script = _trusted_plugin(trusted)
    lookalike = _trusted_plugin(tmp_path / "repository" / "plugins" / "marginal")

    assert not is_control_plane_action(_event(f"python3 {lookalike} status"), trusted)
    assert not is_control_plane_action(
        _event(f"python3 {trusted}/scripts/../scripts/marginal_control.py status"), trusted
    )
    assert not is_control_plane_action(_event(f"python3 {script} status; git status"), trusted)
    assert not is_control_plane_action(_event(f"python3 {script} status && git status"), trusted)
    assert not is_control_plane_action(_event(f"python3 {script} status $(id)"), trusted)
    assert not is_control_plane_action(_event(f"python3 -I {script} status"), trusted)
    assert not is_control_plane_action(_event(f"/usr/bin/env python3 {script} status"), trusted)
    assert not is_control_plane_action(_event(f"/tmp/python3 {script} status"), trusted)

    symlink_target = tmp_path / "outside.py"
    symlink_target.write_text("#!/usr/bin/env python3\n", encoding="utf-8")
    script.unlink()
    os.symlink(symlink_target, script)

    assert not is_control_plane_action(_event(f"python3 {script} status"), trusted)
