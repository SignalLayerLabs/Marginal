from __future__ import annotations

import hashlib
import json
import subprocess
import tarfile
from dataclasses import replace
from pathlib import Path

import pytest
from benchmark.astra.lite.freeze import LiteTask
from benchmark.astra.lite_lane import LiteLaneConfig, _validate_config, prepare_repository, run_lane
from benchmark.codex_adapter.runner import RunConfig, _command


def _git(repo: Path, *args: str, check: bool = True) -> str:
    return subprocess.run(
        ["git", *args], cwd=repo, check=check, capture_output=True, text=True
    ).stdout.strip()


def _git_result(repo: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["git", *args], cwd=repo, check=False, capture_output=True, text=True)


def _repository(tmp_path: Path) -> tuple[Path, str, str]:
    repo = tmp_path / "testbed"
    repo.mkdir(parents=True)
    _git(repo, "init", "-q")
    _git(repo, "config", "user.name", "Lite lane fixture")
    _git(repo, "config", "user.email", "fixture@example.invalid")
    (repo / ".gitignore").write_text(".deps/\n", encoding="utf-8")
    (repo / "base.py").write_text("BASE = True\n", encoding="utf-8")
    (repo / ".deps").mkdir()
    (repo / ".deps" / "tracked.txt").write_text("tracked base file\n", encoding="utf-8")
    _git(repo, "add", ".gitignore", "base.py")
    _git(repo, "add", "-f", ".deps/tracked.txt")
    _git(repo, "commit", "-qm", "base")
    base_commit = _git(repo, "rev-parse", "HEAD")
    (repo / ".deps" / "installed.txt").write_text("keep me\n", encoding="utf-8")
    (repo / ".deps" / "nested" / ".git" / "objects").mkdir(parents=True)
    (repo / ".deps" / "nested" / ".git" / "HEAD").write_text("future history\n", encoding="utf-8")
    (repo / "base.py").write_text("BASE = False\n", encoding="utf-8")
    (repo / "future.py").write_text("SECRET = True\n", encoding="utf-8")
    _git(repo, "add", "base.py", "future.py")
    _git(repo, "commit", "-qm", "future")
    return repo, base_commit, _git(repo, "rev-parse", "HEAD")


def _task(base_commit: str, instance_id: str = "django__django-11099") -> LiteTask:
    return LiteTask(
        instance_id=instance_id,
        repo="django/django",
        base_commit=base_commit,
        official_image="swebench/sweb.eval.x86_64.django_1776_django-11099:latest",
        problem_hash="a" * 64,
        schedule_position=0,
        condition_order=("baseline", "marginal"),
    )


def _config(
    tmp_path: Path, repo: Path, base_commit: str, *, condition: str = "baseline"
) -> LiteLaneConfig:
    prompt = tmp_path / "prompt.txt"
    prompt.write_text("Fix only the public issue.\n", encoding="utf-8")
    auth = tmp_path / "auth.json"
    auth.write_text("{}\n", encoding="utf-8")
    codex = tmp_path / "codex"
    codex.write_text("fixture\n", encoding="utf-8")
    return LiteLaneConfig(
        task=_task(base_commit),
        condition=condition,
        worktree=repo,
        prompt_path=prompt,
        run_dir=tmp_path / "output" / condition,
        codex_executable=codex,
        auth_source=auth,
    )


def _product_archive(tmp_path: Path) -> tuple[Path, str]:
    archive = tmp_path / "marginal.tar"
    source = tmp_path / "product" / "src" / "marginal"
    source.mkdir(parents=True)
    (source / "__init__.py").write_text("PRODUCT = True\n", encoding="utf-8")
    with tarfile.open(archive, "w") as output:
        output.add(source.parent, arcname="src")
    return archive, hashlib.sha256(archive.read_bytes()).hexdigest()


def test_classic_lite_ids_are_accepted_and_pro_or_traversal_ids_are_rejected(
    tmp_path: Path,
) -> None:
    repo, base_commit, _future_commit = _repository(tmp_path)
    config = _config(tmp_path, repo, base_commit)

    _validate_config(replace(config, task=_task(base_commit, "sympy__sympy-12419")))

    for instance_id in (
        "instance_protonmail__webclients-01ea5214d11e0df8b7170d91bafd34f23cb0f2b1",
        "../django__django-11099",
        "django__django-11099/../escape",
    ):
        with pytest.raises(ValueError, match="instance_id"):
            _validate_config(replace(config, task=_task(base_commit, instance_id)))


def test_prepare_repository_recreates_only_the_lite_base_tree(tmp_path: Path) -> None:
    repo, base_commit, future_commit = _repository(tmp_path)
    config = _config(tmp_path, repo, base_commit)
    original_tree = _git(repo, "rev-parse", f"{base_commit}^{{tree}}")

    provenance = prepare_repository(config)

    assert (repo / "base.py").read_text(encoding="utf-8") == "BASE = True\n"
    assert not (repo / "future.py").exists()
    assert (repo / ".deps" / "installed.txt").read_text(encoding="utf-8") == "keep me\n"
    assert not (repo / ".deps" / "nested" / ".git").exists()
    assert _git(repo, "status", "--porcelain", "--untracked-files=all") == ""
    assert _git(repo, "rev-list", "--count", "--all") == "1"
    assert _git_result(repo, "cat-file", "-e", f"{future_commit}^{{commit}}").returncode != 0
    assert provenance.original_base_commit == base_commit
    assert provenance.original_base_tree == original_tree
    assert provenance.snapshot_tree == original_tree


def test_off_and_on_forward_identical_solver_config_except_condition(tmp_path: Path) -> None:
    baseline_repo, base_commit, _future_commit = _repository(tmp_path / "baseline")
    marginal_repo, marginal_base, _marginal_future = _repository(tmp_path / "marginal")
    baseline = _config(tmp_path / "baseline", baseline_repo, base_commit, condition="baseline")
    marginal = _config(tmp_path / "marginal", marginal_repo, marginal_base, condition="marginal")
    archive, digest = _product_archive(tmp_path)
    marginal = replace(marginal, marginal_product_archive=archive, marginal_product_sha256=digest)
    observed: list[RunConfig] = []

    def fake_run_task(run_config: RunConfig) -> dict[str, object]:
        observed.append(run_config)
        run_config.run_dir.mkdir(parents=True)
        return {"run_status": "completed"}

    run_lane(baseline, run_task_fn=fake_run_task)
    run_lane(marginal, run_task_fn=fake_run_task)

    assert len(observed) == 2
    baseline_config, marginal_config = observed
    assert baseline_config.condition == "baseline"
    assert marginal_config.condition == "marginal"
    assert (
        baseline_config.instance_id,
        baseline_config.repetition,
        baseline_config.prompt,
        baseline_config.model,
        baseline_config.reasoning_effort,
        baseline_config.timeout_seconds,
        baseline_config.codex_version,
    ) == (
        marginal_config.instance_id,
        marginal_config.repetition,
        marginal_config.prompt,
        marginal_config.model,
        marginal_config.reasoning_effort,
        marginal_config.timeout_seconds,
        marginal_config.codex_version,
    )
    assert baseline_config.extra_env == {}
    assert marginal_config.extra_env["PYTHONPATH"].endswith("/src")
    shell_environment = {"CODEX_HOME": "/isolated/codex", "HOME": "/isolated/home"}
    assert _command(baseline_config, shell_environment) == _command(
        replace(baseline_config, condition="marginal"), shell_environment
    )
    for run_config in observed:
        provenance = json.loads((run_config.run_dir / "lite-lane.json").read_text(encoding="utf-8"))
        assert provenance["snapshot_commit"] == run_config.expected_base_commit


def test_tampered_product_archive_is_refused_before_solver_execution(tmp_path: Path) -> None:
    repo, base_commit, _future_commit = _repository(tmp_path)
    archive, digest = _product_archive(tmp_path)
    archive.write_bytes(b"tampered")
    config = replace(
        _config(tmp_path, repo, base_commit, condition="marginal"),
        marginal_product_archive=archive,
        marginal_product_sha256=digest,
    )
    launched = False

    def must_not_run(_config: RunConfig) -> dict[str, object]:
        nonlocal launched
        launched = True
        return {"run_status": "completed"}

    with pytest.raises(ValueError, match="digest mismatch"):
        run_lane(config, run_task_fn=must_not_run)
    assert not launched
