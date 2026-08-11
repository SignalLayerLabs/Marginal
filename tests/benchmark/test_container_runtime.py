from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest
from benchmark.codex_adapter.container_runtime import (
    ContainerRunConfig,
    build_container_command,
    official_instance_image,
)

_BASE_COMMIT = "04a523fafbd61bc2e49420963b84ed8e2bd1b3cf"
_BASE_DIGEST = "c8e43bebd10d7d2330820af520361dc6adc9642f98c7b7b7c415cca39852ffdd"
_OVERLAY_DIGEST = "1" * 64
_OVERLAY_IMAGE = f"sha256:{_OVERLAY_DIGEST}"


def _config(tmp_path: Path, *, condition: str = "baseline") -> ContainerRunConfig:
    run_dir = tmp_path / "run"
    run_dir.mkdir(parents=True)
    prompt = run_dir / "prompt.txt"
    prompt.write_text("Fix the issue.\n", encoding="utf-8")
    auth = tmp_path / "auth.json"
    auth.write_text('{"auth_mode":"chatgpt"}\n', encoding="utf-8")
    source = tmp_path / "source"
    (source / "benchmark" / "container").mkdir(parents=True)
    entrypoint = source / "benchmark" / "container" / "entrypoint.sh"
    entrypoint.write_text("#!/bin/sh\n", encoding="utf-8")
    entrypoint.chmod(0o755)
    return ContainerRunConfig(
        instance_id="pvlib__pvlib-python-1072",
        condition=condition,
        expected_base_commit=_BASE_COMMIT,
        task_image=(
            f"swebench/sweb.eval.x86_64.pvlib_1776_pvlib-python-1072@sha256:{_BASE_DIGEST}"
        ),
        overlay_image=_OVERLAY_IMAGE,
        container_name=f"marginal-{condition}-pvlib-1072",
        run_dir=run_dir,
        source_root=source,
        auth_source=auth,
        prompt_file=prompt,
    )


def test_official_image_name_uses_swebench_escape_contract() -> None:
    assert official_instance_image("pvlib__pvlib-python-1072") == (
        "swebench/sweb.eval.x86_64.pvlib_1776_pvlib-python-1072:latest"
    )


def test_container_command_is_digest_pinned_and_contains_no_host_credentials(
    tmp_path: Path,
) -> None:
    config = _config(tmp_path)

    command = build_container_command(config)
    joined = "\n".join(command)

    assert command[:3] == ["docker", "run", "--rm"]
    assert "--platform" in command and "linux/amd64" in command
    assert "--cap-drop=ALL" not in command
    assert "--cap-add=SYS_ADMIN" in command
    assert "no-new-privileges" in command
    assert "seccomp=unconfined" in command
    assert "apparmor=unconfined" in command
    assert "systempaths=unconfined" in command
    assert "MARGINAL_CONDITION=baseline" in command
    assert f"MARGINAL_EXPECTED_BASE_COMMIT={_BASE_COMMIT}" in command
    assert str(config.run_dir.resolve()) in joined
    assert str(config.source_root.resolve()) not in joined
    assert str(config.auth_source.resolve()) in joined
    assert "/run/secrets/codex-auth.json,readonly" in joined
    assert "/opt/marginal/benchmark/container/entrypoint.sh" in joined
    assert config.overlay_image == command[-1]
    assert "OPENAI_API_KEY" not in joined
    assert str(Path.home()) not in joined
    assert config.task_image not in joined


def test_conditions_differ_only_by_explicit_condition_value(tmp_path: Path) -> None:
    baseline = build_container_command(_config(tmp_path / "off", condition="baseline"))
    marginal = build_container_command(_config(tmp_path / "on", condition="marginal"))

    def normalize(command: list[str]) -> list[str]:
        return [
            item.replace("baseline", "LANE")
            .replace("marginal", "LANE")
            .replace(str((tmp_path / "off").resolve()), "ROOT")
            .replace(str((tmp_path / "on").resolve()), "ROOT")
            for item in command
        ]

    assert normalize(baseline) == normalize(marginal)


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("task_image", "swebench/image:latest", "task_image must be digest-pinned"),
        ("overlay_image", "marginal/image:latest", "overlay_image must be digest-pinned"),
        ("condition", "shadow", "condition must be baseline or marginal"),
    ],
)
def test_invalid_container_identity_is_rejected(
    tmp_path: Path, field: str, value: str, message: str
) -> None:
    with pytest.raises(ValueError, match=message):
        replace(_config(tmp_path), **{field: value})


def test_run_dir_must_not_be_inside_source_tree(tmp_path: Path) -> None:
    source = tmp_path / "source"
    (source / "benchmark" / "container").mkdir(parents=True)
    entrypoint = source / "benchmark" / "container" / "entrypoint.sh"
    entrypoint.write_text("#!/bin/sh\n", encoding="utf-8")
    entrypoint.chmod(0o755)
    run_dir = source / "benchmark" / "runs" / "bad"
    run_dir.mkdir(parents=True)
    prompt = run_dir / "prompt.txt"
    prompt.write_text("Fix.\n", encoding="utf-8")
    auth = tmp_path / "auth.json"
    auth.write_text("{}\n", encoding="utf-8")

    with pytest.raises(ValueError, match="run_dir must be outside source_root"):
        ContainerRunConfig(
            instance_id="pvlib__pvlib-python-1072",
            condition="baseline",
            expected_base_commit=_BASE_COMMIT,
            task_image=f"swebench/task@sha256:{_BASE_DIGEST}",
            overlay_image=_OVERLAY_IMAGE,
            container_name="marginal-baseline-pvlib-1072",
            run_dir=run_dir,
            source_root=source,
            auth_source=auth,
            prompt_file=prompt,
        )


def test_entrypoint_enables_native_hooks_for_both_lanes() -> None:
    entrypoint = (
        Path(__file__).resolve().parents[2] / "benchmark" / "container" / "entrypoint.sh"
    ).read_text(encoding="utf-8")

    assert entrypoint.count("--enable codex_hooks") == 1


def test_entrypoint_uses_only_ephemeral_user_hook_configuration() -> None:
    entrypoint = (
        Path(__file__).resolve().parents[2] / "benchmark" / "container" / "entrypoint.sh"
    ).read_text(encoding="utf-8")

    assert "export CODEX_HOME=/marginal-home/.codex" in entrypoint
    assert 'install_project_hooks("/marginal-home"' in entrypoint
    assert "--ignore-user-config" not in entrypoint


def test_entrypoint_places_daemon_socket_on_container_tmpfs() -> None:
    """The macOS-to-VM SSHFS bind cannot host Unix-domain sockets."""

    entrypoint = (
        Path(__file__).resolve().parents[2] / "benchmark" / "container" / "entrypoint.sh"
    ).read_text(encoding="utf-8")

    assert "export MARGINAL_SOCKET=/marginal-home/marginal.sock" in entrypoint
    assert "export MARGINAL_SOCKET=/marginal-run/" not in entrypoint


def test_overlay_records_exact_task_image_provenance() -> None:
    dockerfile = (
        Path(__file__).resolve().parents[2] / "benchmark" / "container" / "Dockerfile.tools"
    ).read_text(encoding="utf-8")

    assert 'org.marginal.task.image="${TASK_IMAGE}"' in dockerfile
