from __future__ import annotations

import json
import subprocess
import sys
import textwrap
from dataclasses import replace
from pathlib import Path

import pytest
from benchmark.codex_adapter.dataset import FrozenTask
from benchmark.codex_adapter.preflight import PreflightConfig, PreflightError, run_preflight


def _git(repo: Path, *args: str) -> str:
    completed = subprocess.run(
        ["git", *args],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
    )
    return completed.stdout.strip()


def _repository(tmp_path: Path) -> tuple[Path, str]:
    repo = tmp_path / "repo"
    (repo / "src" / "marginal").mkdir(parents=True)
    (repo / "src" / "marginal" / "__init__.py").write_text("", encoding="utf-8")
    (repo / "pyproject.toml").write_text("[project]\nname='fixture'\n", encoding="utf-8")
    _git(repo, "init", "-q")
    _git(repo, "config", "user.email", "benchmark@example.invalid")
    _git(repo, "config", "user.name", "Benchmark")
    _git(repo, "add", ".")
    _git(repo, "commit", "-qm", "fixture")
    return repo, _git(repo, "rev-parse", "HEAD")


def _codex(tmp_path: Path, *, version: str = "0.147.0", hooks: bool = True) -> Path:
    executable = tmp_path / f"codex-{version}-{hooks}"
    executable.write_text(
        textwrap.dedent(
            f"""\
            #!/usr/bin/env python3
            import json
            import sys

            args = sys.argv[1:]
            if args == ["--version"]:
                print("codex-cli {version}")
            elif args == ["features", "list"]:
                print("hooks stable {"true" if hooks else "false"}")
            elif args == ["debug", "models", "--bundled"]:
                print(json.dumps({{"models": [{{
                    "slug": "gpt-5.6-sol",
                    "supported_reasoning_levels": [{{"effort": "high"}}],
                }}]}}))
            elif args == ["login", "status"]:
                print("Logged in using ChatGPT")
            else:
                raise SystemExit(2)
            """
        ),
        encoding="utf-8",
    )
    executable.chmod(0o755)
    return executable


def _config(tmp_path: Path, *, version: str = "0.147.0", hooks: bool = True) -> PreflightConfig:
    repo, commit = _repository(tmp_path)
    prompt = tmp_path / "prompt.txt"
    prompt.write_text("{{problem_statement}}\n", encoding="utf-8")
    prompt_hash = __import__("hashlib").sha256(prompt.read_bytes()).hexdigest()
    environment = tmp_path / "environment.json"
    environment.write_text(
        json.dumps(
            {
                "repository": {"commit": commit},
                "python": "3.13.0",
                "codex": {
                    "cli_version": "0.147.0",
                    "model": "gpt-5.6-sol",
                    "reasoning_effort": "high",
                },
                "benchmark": {"prompt_template_sha256": prompt_hash},
            }
        ),
        encoding="utf-8",
    )
    tasks = tmp_path / "tasks.json"
    tasks.write_text(json.dumps({"task_ids": ["owner__repo-1"]}), encoding="utf-8")
    schema = tmp_path / "schema.json"
    schema.write_text(
        json.dumps({"$schema": "https://json-schema.org/draft/2020-12/schema", "type": "object"}),
        encoding="utf-8",
    )
    auth = tmp_path / "auth.json"
    auth.write_text("{}", encoding="utf-8")
    auth.chmod(0o600)
    return PreflightConfig(
        repository_root=repo,
        codex_executable=_codex(tmp_path, version=version, hooks=hooks),
        python_executable=Path(sys.executable),
        auth_source=auth,
        environment_path=environment,
        tasks_path=tasks,
        prompt_path=prompt,
        schema_path=schema,
        expected_repository_commit=commit,
        require_verifier=False,
        require_task_environment=False,
    )


def _tasks() -> tuple[FrozenTask, ...]:
    return (FrozenTask("owner__repo-1", "owner/repo", "a" * 40, "Fix it.", ""),)


def test_preflight_confirms_pinned_runtime_and_frozen_inputs(tmp_path: Path) -> None:
    report = run_preflight(_config(tmp_path), task_loader=lambda _: _tasks())

    assert report["ready"] is True
    assert report["codex_version"] == "0.147.0"
    assert report["model"] == "gpt-5.6-sol"
    assert report["reasoning_effort"] == "high"
    assert report["task_ids"] == ["owner__repo-1"]
    assert report["credentials_recorded"] is False


def test_version_mismatch_and_disabled_hooks_fail_closed(tmp_path: Path) -> None:
    with pytest.raises(PreflightError, match="Codex version"):
        run_preflight(
            _config(tmp_path / "version", version="0.146.0"), task_loader=lambda _: _tasks()
        )

    with pytest.raises(PreflightError, match="hooks feature"):
        run_preflight(_config(tmp_path / "hooks", hooks=False), task_loader=lambda _: _tasks())


def test_dirty_marginal_core_fails_closed(tmp_path: Path) -> None:
    config = _config(tmp_path)
    (config.repository_root / "src" / "marginal" / "__init__.py").write_text(
        "DIRTY = True\n", encoding="utf-8"
    )

    with pytest.raises(PreflightError, match="core source is dirty"):
        run_preflight(config, task_loader=lambda _: _tasks())


def test_full_preflight_blocks_bare_host_task_execution(tmp_path: Path) -> None:
    config = replace(_config(tmp_path), require_task_environment=True)

    with pytest.raises(PreflightError, match="per-instance Codex execution backend"):
        run_preflight(config, task_loader=lambda _: _tasks())
