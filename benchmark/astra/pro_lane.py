"""Execute one SWE-bench Pro lane inside its disposable task container."""

from __future__ import annotations

import argparse
import contextlib
import json
import os
import re
import shutil
import subprocess
import tempfile
from collections.abc import Callable, Sequence
from dataclasses import asdict, dataclass, replace
from pathlib import Path, PurePosixPath
from typing import Any

from benchmark.codex_adapter.runner import RunConfig, run_task

_INSTANCE_ID = re.compile(
    r"^instance_[A-Za-z0-9][A-Za-z0-9._-]*__[A-Za-z0-9][A-Za-z0-9._-]*-"
    r"[0-9a-f]{40}(?:-v(?:[0-9a-f]{40}|nan))?$"
)
_COMMIT = re.compile(r"^[0-9a-f]{40}$")
_CONDITIONS = frozenset({"baseline", "marginal"})
RunTask = Callable[[RunConfig], dict[str, Any]]


@dataclass(frozen=True, slots=True)
class ProLaneConfig:
    instance_id: str
    base_commit: str
    condition: str
    worktree: Path = Path("/app")
    prompt_path: Path = Path("/marginal-input/prompt.txt")
    run_dir: Path = Path("/marginal-output/lane")
    codex_executable: Path = Path("/opt/marginal-tools/bin/codex")
    auth_source: Path = Path("/run/secrets/codex-auth.json")


@dataclass(frozen=True, slots=True)
class SnapshotProvenance:
    original_base_commit: str
    original_base_tree: str
    snapshot_commit: str
    snapshot_tree: str


def _git(
    worktree: Path,
    *args: str,
    env: dict[str, str] | None = None,
    text: bool = True,
) -> str | bytes:
    completed = subprocess.run(
        ["git", *args],
        cwd=worktree,
        env=env,
        capture_output=True,
        check=False,
        text=text,
        timeout=120,
    )
    if completed.returncode != 0:
        stderr = completed.stderr if text else completed.stderr.decode("utf-8", errors="replace")
        raise RuntimeError(f"git {' '.join(args)} failed: {stderr.strip()}")
    return completed.stdout


def _absolute(path: Path, label: str) -> Path:
    if not path.is_absolute():
        raise ValueError(f"{label} must be an absolute path")
    return path.resolve()


def _validate_config(config: ProLaneConfig) -> ProLaneConfig:
    if _INSTANCE_ID.fullmatch(config.instance_id) is None:
        raise ValueError("instance_id is not a valid SWE-bench instance ID")
    if _COMMIT.fullmatch(config.base_commit) is None:
        raise ValueError("base_commit must be a lowercase 40-character SHA")
    if config.condition not in _CONDITIONS:
        raise ValueError("condition must be baseline or marginal")

    worktree = _absolute(config.worktree, "worktree")
    prompt_path = _absolute(config.prompt_path, "prompt path")
    run_dir = _absolute(config.run_dir, "run directory")
    codex_executable = _absolute(config.codex_executable, "Codex executable")
    auth_source = _absolute(config.auth_source, "auth source")
    if not worktree.is_dir():
        raise ValueError(f"worktree does not exist: {worktree}")
    for label, path in (
        ("prompt", prompt_path),
        ("Codex executable", codex_executable),
        ("auth source", auth_source),
    ):
        if not path.is_file():
            raise ValueError(f"{label} does not exist: {path}")
        if path.is_relative_to(worktree):
            raise ValueError(f"{label} must be outside the task repository")
    if run_dir.exists():
        raise FileExistsError(f"run directory already exists: {run_dir}")
    if run_dir == worktree or run_dir.is_relative_to(worktree):
        raise ValueError("run directory must be outside the task repository")

    try:
        top_level = str(_git(worktree, "rev-parse", "--show-toplevel")).strip()
        resolved_commit = str(
            _git(worktree, "rev-parse", f"{config.base_commit}^{{commit}}")
        ).strip()
    except RuntimeError as exc:
        raise ValueError(f"task repository validation failed: {exc}") from exc
    if Path(top_level).resolve() != worktree:
        raise ValueError("worktree must be the task repository root")
    if resolved_commit != config.base_commit:
        raise ValueError("base_commit did not resolve to the exact requested commit")
    tree_entries = _git(worktree, "ls-tree", "-r", "-z", config.base_commit, text=False)
    assert isinstance(tree_entries, bytes)
    for entry in tree_entries.split(b"\0"):
        if entry.startswith(b"160000 commit "):
            raise ValueError("base_commit contains an unsupported gitlink")
    return replace(
        config,
        worktree=worktree,
        prompt_path=prompt_path,
        run_dir=run_dir,
        codex_executable=codex_executable,
        auth_source=auth_source,
    )


def _remove_tracked_files(worktree: Path) -> None:
    raw = _git(worktree, "ls-files", "-z", text=False)
    assert isinstance(raw, bytes)
    tracked = raw.decode("utf-8", errors="surrogateescape").split("\0")
    by_depth = sorted(
        (item for item in tracked if item),
        key=lambda item: item.count("/"),
        reverse=True,
    )
    for relative in by_depth:
        pure = PurePosixPath(relative)
        if pure.is_absolute() or ".." in pure.parts:
            raise RuntimeError(f"unsafe tracked path: {relative!r}")
        target = worktree.joinpath(*pure.parts)
        if target.is_symlink() or target.is_file():
            target.unlink()
        elif target.is_dir():
            with contextlib.suppress(OSError):
                target.rmdir()


def _extract_archive(archive: Path, worktree: Path) -> None:
    completed = subprocess.run(
        ["tar", "-xf", str(archive), "-C", str(worktree)],
        capture_output=True,
        check=False,
        text=True,
        timeout=120,
    )
    if completed.returncode != 0:
        raise RuntimeError(f"base archive extraction failed: {completed.stderr.strip()}")


def _remove_git_metadata(metadata: Path) -> None:
    if metadata.is_dir() and not metadata.is_symlink():
        shutil.rmtree(metadata)
    elif metadata.exists() or metadata.is_symlink():
        metadata.unlink()


def _purge_git_metadata(worktree: Path) -> None:
    for root, directories, files in os.walk(worktree, topdown=True, followlinks=False):
        if ".git" in directories:
            _remove_git_metadata(Path(root) / ".git")
            directories.remove(".git")
        if ".git" in files:
            _remove_git_metadata(Path(root) / ".git")


def prepare_repository(config: ProLaneConfig) -> SnapshotProvenance:
    """Replace the task checkout with a detached one-commit base snapshot."""

    config = _validate_config(config)
    original_tree = str(
        _git(config.worktree, "rev-parse", f"{config.base_commit}^{{tree}}")
    ).strip()
    with tempfile.TemporaryDirectory(prefix="marginal-pro-base-") as temporary:
        archive = Path(temporary) / "base.tar"
        _git(
            config.worktree,
            "archive",
            "--format=tar",
            f"--output={archive}",
            config.base_commit,
        )

        _git(config.worktree, "clean", "-ffd")
        _remove_tracked_files(config.worktree)
        _extract_archive(archive, config.worktree)
        _purge_git_metadata(config.worktree)

    _git(config.worktree, "init", "-q")
    _git(config.worktree, "add", "-A")
    commit_environment = dict(os.environ)
    commit_environment.update(
        {
            "GIT_AUTHOR_NAME": "MARGINAL Pro Benchmark",
            "GIT_AUTHOR_EMAIL": "benchmark@example.invalid",
            "GIT_AUTHOR_DATE": "2000-01-01T00:00:00+00:00",
            "GIT_COMMITTER_NAME": "MARGINAL Pro Benchmark",
            "GIT_COMMITTER_EMAIL": "benchmark@example.invalid",
            "GIT_COMMITTER_DATE": "2000-01-01T00:00:00+00:00",
        }
    )
    _git(config.worktree, "commit", "-qm", "frozen SWE-bench Pro base", env=commit_environment)
    _git(config.worktree, "checkout", "--detach", "-q", "HEAD")
    snapshot_commit = str(_git(config.worktree, "rev-parse", "HEAD")).strip()
    snapshot_tree = str(_git(config.worktree, "rev-parse", "HEAD^{tree}")).strip()
    if snapshot_tree != original_tree:
        raise RuntimeError(f"snapshot tree mismatch: expected {original_tree}, got {snapshot_tree}")
    if str(_git(config.worktree, "status", "--porcelain", "--untracked-files=all")):
        raise RuntimeError("fresh task snapshot is not clean")
    if str(_git(config.worktree, "rev-list", "--count", "--all")).strip() != "1":
        raise RuntimeError("fresh task snapshot contains more than one commit")
    return SnapshotProvenance(
        original_base_commit=config.base_commit,
        original_base_tree=original_tree,
        snapshot_commit=snapshot_commit,
        snapshot_tree=snapshot_tree,
    )


def run_lane(
    config: ProLaneConfig,
    *,
    run_task_fn: RunTask = run_task,
) -> dict[str, Any]:
    """Prepare and execute one fixed-contract Pro solver lane."""

    config = _validate_config(config)
    provenance = prepare_repository(config)
    prompt = config.prompt_path.read_text(encoding="utf-8")
    record = run_task_fn(
        RunConfig(
            instance_id=config.instance_id,
            condition=config.condition,
            repetition=1,
            worktree=config.worktree,
            expected_base_commit=provenance.snapshot_commit,
            run_dir=config.run_dir,
            prompt=prompt,
            codex_executable=config.codex_executable,
            auth_source=config.auth_source,
            model="gpt-6-astra",
            reasoning_effort="medium",
            timeout_seconds=900,
            codex_version="0.153.4",
        )
    )
    provenance_path = config.run_dir / "pro-lane.json"
    with provenance_path.open("x", encoding="utf-8") as output:
        json.dump(asdict(provenance), output, indent=2, sort_keys=True)
        output.write("\n")
    return record


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--instance-id", required=True)
    parser.add_argument("--base-commit", required=True)
    parser.add_argument("--condition", required=True, choices=sorted(_CONDITIONS))
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    config = ProLaneConfig(
        instance_id=args.instance_id,
        base_commit=args.base_commit,
        condition=args.condition,
    )
    record = run_lane(config)
    print(
        json.dumps(
            {
                "instance_id": config.instance_id,
                "condition": config.condition,
                "run_status": record.get("run_status"),
                "run_dir": str(config.run_dir),
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
