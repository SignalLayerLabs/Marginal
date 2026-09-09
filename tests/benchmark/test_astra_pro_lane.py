from __future__ import annotations

import json
import subprocess
from dataclasses import replace
from pathlib import Path

import pytest
from benchmark.astra.pro_lane import ProLaneConfig, _validate_config, prepare_repository, run_lane
from benchmark.codex_adapter.runner import RunConfig


def _git(repo: Path, *args: str, check: bool = True) -> str:
    return subprocess.run(
        ["git", *args],
        cwd=repo,
        check=check,
        capture_output=True,
        text=True,
    ).stdout.strip()


def _git_result(repo: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["git", *args], cwd=repo, check=False, capture_output=True, text=True)


def _repository(tmp_path: Path) -> tuple[Path, str, str]:
    repo = tmp_path / "app"
    repo.mkdir()
    _git(repo, "init", "-q")
    _git(repo, "config", "user.name", "Pro lane fixture")
    _git(repo, "config", "user.email", "fixture@example.invalid")
    (repo / ".gitignore").write_text(".deps/\n", encoding="utf-8")
    (repo / "base.py").write_text("BASE = True\n", encoding="utf-8")
    _git(repo, "add", ".gitignore", "base.py")
    _git(repo, "commit", "-qm", "base")
    base_commit = _git(repo, "rev-parse", "HEAD")
    (repo / ".deps").mkdir()
    (repo / ".deps" / "installed.txt").write_text("keep me\n", encoding="utf-8")
    (repo / ".deps" / "nested" / ".git" / "objects").mkdir(parents=True)
    (repo / ".deps" / "nested" / ".git" / "HEAD").write_text(
        "ref: refs/heads/future\n", encoding="utf-8"
    )
    (repo / "base.py").write_text("BASE = False\n", encoding="utf-8")
    (repo / "future.py").write_text("SECRET = True\n", encoding="utf-8")
    _git(repo, "add", "base.py", "future.py")
    _git(repo, "commit", "-qm", "future")
    return repo, base_commit, _git(repo, "rev-parse", "HEAD")


def _config(tmp_path: Path, repo: Path, base_commit: str) -> ProLaneConfig:
    prompt = tmp_path / "prompt.txt"
    prompt.write_text("Fix only the public issue.\n", encoding="utf-8")
    auth = tmp_path / "auth.json"
    auth.write_text("{}\n", encoding="utf-8")
    codex = tmp_path / "codex"
    codex.write_text("fixture\n", encoding="utf-8")
    return ProLaneConfig(
        instance_id="instance_protonmail__webclients-01ea5214d11e0df8b7170d91bafd34f23cb0f2b1",
        base_commit=base_commit,
        condition="marginal",
        worktree=repo,
        prompt_path=prompt,
        run_dir=tmp_path / "output" / "lane",
        codex_executable=codex,
        auth_source=auth,
    )


def test_prepare_repository_keeps_only_the_base_tree_and_ignored_dependencies(
    tmp_path: Path,
) -> None:
    repo, base_commit, future_commit = _repository(tmp_path)
    config = _config(tmp_path, repo, base_commit)
    original_tree = _git(repo, "rev-parse", f"{base_commit}^{{tree}}")

    provenance = prepare_repository(config)

    assert (repo / "base.py").read_text(encoding="utf-8") == "BASE = True\n"
    assert not (repo / "future.py").exists()
    assert (repo / ".deps" / "installed.txt").read_text(encoding="utf-8") == "keep me\n"
    assert not (repo / ".deps" / "nested" / ".git").exists()
    assert _git(repo, "status", "--porcelain", "--untracked-files=all") == ""
    assert _git(repo, "rev-parse", "--abbrev-ref", "HEAD") == "HEAD"
    assert _git(repo, "rev-list", "--count", "--all") == "1"
    assert _git_result(repo, "cat-file", "-e", f"{future_commit}^{{commit}}").returncode != 0
    assert provenance.original_base_commit == base_commit
    assert provenance.original_base_tree == original_tree
    assert provenance.snapshot_commit == _git(repo, "rev-parse", "HEAD")
    assert provenance.snapshot_tree == original_tree


def test_base_gitlink_is_rejected_before_any_repository_mutation(tmp_path: Path) -> None:
    repo, _base_commit, _future_commit = _repository(tmp_path)
    linked_commit = _git(repo, "rev-parse", "HEAD")
    _git(repo, "update-index", "--add", "--cacheinfo", f"160000,{linked_commit},vendor/sub")
    _git(repo, "commit", "-qm", "add gitlink")
    gitlink_base = _git(repo, "rev-parse", "HEAD")
    nested_git = repo / "vendor" / "sub" / ".git"
    nested_git.mkdir(parents=True)
    (nested_git / "HEAD").write_text("future history\n", encoding="utf-8")
    config = _config(tmp_path, repo, gitlink_base)

    with pytest.raises(ValueError, match="gitlink"):
        prepare_repository(config)

    assert _git(repo, "rev-parse", "HEAD") == gitlink_base
    assert nested_git.is_dir()


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        (lambda config: replace(config, instance_id="../escape"), "instance_id"),
        (lambda config: replace(config, base_commit="A" * 40), "base_commit"),
        (lambda config: replace(config, prompt_path=Path("prompt.txt")), "absolute"),
    ],
)
def test_invalid_public_inputs_are_rejected_before_repository_mutation(
    tmp_path: Path,
    mutation: object,
    message: str,
) -> None:
    repo, base_commit, future_commit = _repository(tmp_path)
    config = mutation(_config(tmp_path, repo, base_commit))  # type: ignore[operator]

    with pytest.raises(ValueError, match=message):
        prepare_repository(config)

    assert _git(repo, "rev-parse", "HEAD") == future_commit
    assert (repo / "future.py").is_file()


def test_existing_run_directory_is_rejected_before_repository_mutation(tmp_path: Path) -> None:
    repo, base_commit, future_commit = _repository(tmp_path)
    config = _config(tmp_path, repo, base_commit)
    config.run_dir.mkdir(parents=True)
    (config.run_dir / "existing.json").write_text("do not overwrite\n", encoding="utf-8")

    with pytest.raises(FileExistsError, match="run directory"):
        run_lane(config, run_task_fn=lambda _: {})

    assert _git(repo, "rev-parse", "HEAD") == future_commit
    assert (config.run_dir / "existing.json").read_text(encoding="utf-8") == "do not overwrite\n"


def test_run_lane_forwards_fixed_solver_contract_and_records_hashes(tmp_path: Path) -> None:
    repo, base_commit, _future_commit = _repository(tmp_path)
    config = _config(tmp_path, repo, base_commit)
    observed: list[RunConfig] = []

    def fake_run_task(run_config: RunConfig) -> dict[str, object]:
        observed.append(run_config)
        run_config.run_dir.mkdir(parents=True)
        return {"run_status": "completed", "instance_id": run_config.instance_id}

    record = run_lane(config, run_task_fn=fake_run_task)

    assert record == {
        "run_status": "completed",
        "instance_id": "instance_protonmail__webclients-01ea5214d11e0df8b7170d91bafd34f23cb0f2b1",
    }
    assert len(observed) == 1
    forwarded = observed[0]
    assert forwarded.instance_id == (
        "instance_protonmail__webclients-01ea5214d11e0df8b7170d91bafd34f23cb0f2b1"
    )
    assert forwarded.condition == "marginal"
    assert forwarded.repetition == 1
    assert forwarded.worktree == repo.resolve()
    assert forwarded.expected_base_commit == _git(repo, "rev-parse", "HEAD")
    assert forwarded.run_dir == config.run_dir.resolve()
    assert forwarded.prompt == "Fix only the public issue.\n"
    assert forwarded.codex_executable == config.codex_executable
    assert forwarded.auth_source == config.auth_source
    assert forwarded.model == "gpt-6-astra"
    assert forwarded.reasoning_effort == "medium"
    assert forwarded.timeout_seconds == 900
    assert forwarded.codex_version == "0.153.4"
    provenance = json.loads((config.run_dir / "pro-lane.json").read_text(encoding="utf-8"))
    assert provenance["original_base_commit"] == base_commit
    assert provenance["snapshot_commit"] == forwarded.expected_base_commit
    assert provenance["original_base_tree"] == provenance["snapshot_tree"]


def test_manifest_instance_ids_are_accepted_and_unsafe_ids_are_rejected(tmp_path: Path) -> None:
    repo, base_commit, _future_commit = _repository(tmp_path)
    config = _config(tmp_path, repo, base_commit)
    manifest = (
        Path(__file__).resolve().parents[2] / "benchmark" / "astra" / "pro" / "task-manifest.jsonl"
    )
    instance_ids = [json.loads(line)["instance_id"] for line in manifest.read_text().splitlines()]

    for instance_id in instance_ids:
        _validate_config(replace(config, instance_id=instance_id))

    for instance_id in ("", "../escape", "instance_foo__bar-abc def", " instance_foo__bar-abc"):
        with pytest.raises(ValueError, match="instance_id"):
            _validate_config(replace(config, instance_id=instance_id))
