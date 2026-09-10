"""Execute one SWE-bench Lite lane inside its disposable task container."""

from __future__ import annotations

import argparse
import contextlib
import hashlib
import json
import re
import tarfile
import tempfile
from collections.abc import Callable, Sequence
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import Any

from benchmark.astra._snapshot import SnapshotProvenance, _git, prepare_exact_tree
from benchmark.astra.lite.freeze import LiteTask
from benchmark.codex_adapter.runner import RunConfig, run_task

_CLASSIC_INSTANCE_ID = re.compile(
    r"^[A-Za-z0-9][A-Za-z0-9._-]*__[A-Za-z0-9][A-Za-z0-9._-]*-[0-9]+$"
)
_COMMIT = re.compile(r"^[0-9a-f]{40}$")
_CONDITIONS = frozenset({"baseline", "marginal"})
RunTask = Callable[[RunConfig], dict[str, Any]]


@dataclass(frozen=True, slots=True)
class LiteLaneConfig:
    task: LiteTask
    condition: str
    worktree: Path = Path("/testbed")
    prompt_path: Path = Path("/marginal-input/prompt.txt")
    run_dir: Path = Path("/marginal-output/lane")
    codex_executable: Path = Path("/opt/marginal-tools/bin/codex")
    auth_source: Path = Path("/run/secrets/codex-auth.json")
    marginal_product_archive: Path | None = None
    marginal_product_sha256: str | None = None


def _absolute(path: Path, label: str) -> Path:
    if not path.is_absolute():
        raise ValueError(f"{label} must be an absolute path")
    return path.resolve()


def _validate_config(config: LiteLaneConfig) -> LiteLaneConfig:
    if _CLASSIC_INSTANCE_ID.fullmatch(config.task.instance_id) is None:
        raise ValueError("instance_id is not a valid classic SWE-bench Lite instance ID")
    if _COMMIT.fullmatch(config.task.base_commit) is None:
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
            _git(worktree, "rev-parse", f"{config.task.base_commit}^{{commit}}")
        ).strip()
    except RuntimeError as exc:
        raise ValueError(f"task repository validation failed: {exc}") from exc
    if Path(top_level).resolve() != worktree:
        raise ValueError("worktree must be the task repository root")
    if resolved_commit != config.task.base_commit:
        raise ValueError("base_commit did not resolve to the exact requested commit")
    tree_entries = _git(worktree, "ls-tree", "-r", "-z", config.task.base_commit, text=False)
    assert isinstance(tree_entries, bytes)
    if any(entry.startswith(b"160000 commit ") for entry in tree_entries.split(b"\0")):
        raise ValueError("base_commit contains an unsupported gitlink")
    return replace(
        config,
        worktree=worktree,
        prompt_path=prompt_path,
        run_dir=run_dir,
        codex_executable=codex_executable,
        auth_source=auth_source,
    )


def prepare_repository(config: LiteLaneConfig) -> SnapshotProvenance:
    """Replace the Lite task checkout with a detached one-commit base snapshot."""

    config = _validate_config(config)
    return prepare_exact_tree(config.worktree, config.task.base_commit, lane_name="Lite")


def run_lane(config: LiteLaneConfig, *, run_task_fn: RunTask = run_task) -> dict[str, Any]:
    """Prepare and execute one fixed-contract Lite solver lane."""

    config = _validate_config(config)
    product_context = contextlib.nullcontext(None)
    if config.condition == "marginal":
        if config.marginal_product_archive is None or config.marginal_product_sha256 is None:
            raise ValueError("marginal lane requires frozen product archive provenance")
        try:
            actual = hashlib.sha256(config.marginal_product_archive.read_bytes()).hexdigest()
        except OSError as exc:
            raise ValueError("frozen product archive is unreadable") from exc
        if actual != config.marginal_product_sha256:
            raise ValueError("frozen product archive digest mismatch")
        product_context = tempfile.TemporaryDirectory(prefix="lite-product-")
    provenance = prepare_repository(config)
    prompt = config.prompt_path.read_text(encoding="utf-8")
    with product_context as product_root:
        extra_env: dict[str, str] = {}
        if product_root is not None:
            try:
                with tarfile.open(config.marginal_product_archive) as archive:
                    members = archive.getmembers()
                    if any(
                        Path(member.name).is_absolute() or ".." in Path(member.name).parts
                        for member in members
                    ):
                        raise ValueError("frozen product archive contains an unsafe path")
                    archive.extractall(product_root, members=members, filter="data")
            except (OSError, tarfile.TarError) as exc:
                raise ValueError("frozen product archive is unreadable") from exc
            source = Path(product_root) / "src"
            if not (source / "marginal").is_dir():
                raise ValueError("frozen product archive lacks src/marginal")
            extra_env["PYTHONPATH"] = str(source)
        record = run_task_fn(
            RunConfig(
                instance_id=config.task.instance_id,
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
                extra_env=extra_env,
            )
        )
    provenance_path = config.run_dir / "lite-lane.json"
    payload = {
        **asdict(provenance),
        "instance_id": config.task.instance_id,
        "repo": config.task.repo,
        "problem_hash": config.task.problem_hash,
        "rendered_prompt_sha256": hashlib.sha256(prompt.encode("utf-8")).hexdigest(),
    }
    with provenance_path.open("x", encoding="utf-8") as output:
        json.dump(payload, output, indent=2, sort_keys=True)
        output.write("\n")
    return record


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--instance-id", required=True)
    parser.add_argument("--repo", required=True)
    parser.add_argument("--base-commit", required=True)
    parser.add_argument("--official-image", required=True)
    parser.add_argument("--problem-hash", required=True)
    parser.add_argument("--schedule-position", required=True, type=int)
    parser.add_argument("--condition", required=True, choices=sorted(_CONDITIONS))
    parser.add_argument("--run-dir", type=Path, default=Path("/marginal-output/lane"))
    parser.add_argument("--marginal-product-archive", type=Path)
    parser.add_argument("--marginal-product-sha256")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    config = LiteLaneConfig(
        task=LiteTask(
            instance_id=args.instance_id,
            repo=args.repo,
            base_commit=args.base_commit,
            official_image=args.official_image,
            problem_hash=args.problem_hash,
            schedule_position=args.schedule_position,
            condition_order=("baseline", "marginal"),
        ),
        condition=args.condition,
        run_dir=args.run_dir,
        marginal_product_archive=args.marginal_product_archive,
        marginal_product_sha256=args.marginal_product_sha256,
    )
    record = run_lane(config)
    print(
        json.dumps(
            {
                "instance_id": config.task.instance_id,
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
