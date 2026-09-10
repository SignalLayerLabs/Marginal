"""Resumable, immutable orchestrator for the paired SWE-bench Lite campaign.

The campaign checkpoint intentionally contains task identity and image provenance, never issue
text, benchmark test material, other-lane inputs, or authentication.  Docker and issue access
are dependency-injected so unit tests never need a daemon, a dataset, or Codex inference.
"""

from __future__ import annotations

import argparse
import contextlib
import hashlib
import json
import os
import subprocess
import tempfile
from collections.abc import Callable, Mapping, Sequence
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Protocol

from benchmark.astra.lite.checkpoint import (
    CampaignCheckpoint,
    CheckpointError,
    atomic_create_bytes,
    read_json,
)
from benchmark.astra.lite.freeze import LiteTask, load_safe_manifest


class CampaignError(RuntimeError):
    """Raised when campaign integrity or the solver isolation boundary is violated."""


@dataclass(frozen=True, slots=True)
class ScheduleEntry:
    task: LiteTask
    condition: str


@dataclass(frozen=True, slots=True)
class PreparedTask:
    """Digest-pinned task and locally-built overlay image identities."""

    task_image: str
    overlay_image: str


@dataclass(frozen=True, slots=True)
class RunSummary:
    launched: int
    stop_reason: str | None


class LaneRuntime(Protocol):
    def prepare(self, task: LiteTask) -> PreparedTask: ...

    def run_lane(
        self,
        task: LiteTask,
        condition: str,
        prepared: PreparedTask,
        lane_dir: Path,
        solver_input: str,
    ) -> Mapping[str, Any]: ...

    def remove_image(self, image: str) -> None: ...


ProblemProvider = Callable[[LiteTask], Mapping[str, str]]


def render_solver_input(
    task: LiteTask, projected: Mapping[str, str], *, prompt_path: Path | None = None
) -> str:
    """Render only a hash-verified issue statement into the frozen prompt template."""

    if set(projected) != {"instance_id", "problem_statement"}:
        raise CampaignError("problem projection must contain only allowlisted fields")
    instance_id = projected["instance_id"]
    problem = projected["problem_statement"]
    if instance_id != task.instance_id or not isinstance(problem, str) or not problem:
        raise CampaignError("problem projection does not match the frozen task identity")
    if hashlib.sha256(problem.encode("utf-8")).hexdigest() != task.problem_hash:
        raise CampaignError("problem projection hash does not match frozen problem_hash")
    template_file = prompt_path or Path(__file__).resolve().parents[1] / "prompt_template.txt"
    try:
        template = template_file.read_text(encoding="utf-8")
    except OSError as exc:
        raise CampaignError("frozen solver prompt is unreadable") from exc
    if template.count("{{problem_statement}}") != 1:
        raise CampaignError("frozen solver prompt has an invalid issue placeholder")
    return template.replace("{{problem_statement}}", problem)


class Campaign:
    """Read-only view over an initialized immutable schedule."""

    def __init__(self, checkpoint: CampaignCheckpoint):
        self.checkpoint = checkpoint
        self.tasks = checkpoint.tasks()

    @classmethod
    def open(cls, root: str | Path) -> Campaign:
        return cls(CampaignCheckpoint(Path(root)))

    def entries(self) -> tuple[ScheduleEntry, ...]:
        return tuple(
            ScheduleEntry(task, condition)
            for task in self.tasks
            for condition in task.condition_order
        )

    def next_entries(self) -> tuple[ScheduleEntry, ...]:
        return tuple(
            entry
            for entry in self.entries()
            if not self.checkpoint.has_attempt(entry.task, entry.condition)
        )

    def status(self) -> dict[str, int]:
        entries = self.entries()
        attempted = sum(
            self.checkpoint.has_attempt(entry.task, entry.condition) for entry in entries
        )
        completed = 0
        quota = 0
        infrastructure = 0
        for entry in entries:
            outcome = self.checkpoint.lane_dir(entry.task, entry.condition) / "outcome.json"
            if outcome.is_file():
                value = read_json(outcome)
                completed += 1
                quota += value.get("category") == "quota"
                infrastructure += value.get("category") == "infrastructure"
        return {
            "scheduled": len(entries),
            "attempted": attempted,
            "unfinished": len(entries) - attempted,
            "finished": completed,
            "quota_stops": quota,
            "infrastructure_failures": infrastructure,
        }


def initialize_campaign(root: str | Path, tasks: tuple[LiteTask, ...]) -> Campaign:
    checkpoint = CampaignCheckpoint(Path(root))
    checkpoint.initialize(tasks)
    return Campaign(checkpoint)


def _outcome_category(record: Mapping[str, Any] | None, error: BaseException | None) -> str:
    if error is not None:
        return "infrastructure"
    status = str((record or {}).get("run_status", ""))
    lowered = status.lower()
    if "quota" in lowered or "capacity" in lowered:
        return "quota"
    if "infra" in lowered or "integration" in lowered or "security" in lowered:
        return "infrastructure"
    return "task"


class CampaignRunner:
    """Launch each unclaimed lane once, retaining uncertain state rather than retrying it."""

    def __init__(self, root: str | Path, runtime: LaneRuntime, problem_provider: ProblemProvider):
        self.checkpoint = CampaignCheckpoint(Path(root))
        self.runtime = runtime
        self.problem_provider = problem_provider

    def _prepared(self, task: LiteTask) -> PreparedTask:
        recorded = self.checkpoint.read_prepared(task)
        if recorded is not None:
            return PreparedTask(**recorded)
        prepared = self.runtime.prepare(task)
        values = asdict(prepared)
        try:
            self.checkpoint.record_prepared(task, values)
        except CheckpointError:
            # A concurrent runner may have won the immutable task preparation race.
            existing = self.checkpoint.read_prepared(task)
            if existing is None:
                raise
            return PreparedTask(**existing)
        return prepared

    def _cleanup_if_paired(self, task: LiteTask, prepared: PreparedTask) -> None:
        if not all(
            self.checkpoint.has_attempt(task, condition) for condition in task.condition_order
        ):
            return
        # Explicit identities only; never use a broad Docker prune operation.
        self.runtime.remove_image(prepared.overlay_image)
        self.runtime.remove_image(prepared.task_image)

    def run(self, *, max_lanes: int) -> RunSummary:
        if max_lanes <= 0:
            raise CampaignError("max_lanes must be positive")
        campaign = Campaign(self.checkpoint)
        launched = 0
        for entry in campaign.next_entries():
            if launched >= max_lanes:
                break
            prepared = self._prepared(entry.task)
            # The provider is permitted to project only the issue text, then it is hash checked
            # before being supplied to the disposable lane.
            solver_input = render_solver_input(entry.task, self.problem_provider(entry.task))
            lane = self.checkpoint.claim_attempt(entry.task, entry.condition, asdict(prepared))
            if lane is None:
                continue
            launched += 1
            record: Mapping[str, Any] | None = None
            failure: BaseException | None = None
            try:
                record = self.runtime.run_lane(
                    entry.task, entry.condition, prepared, lane, solver_input
                )
            except Exception as exc:
                failure = exc
            category = _outcome_category(record, failure)
            patch = _patch_path(lane)
            if not patch.exists():
                atomic_create_bytes(lane / "model.patch", b"")
            outcome: dict[str, Any] = {
                "schema_version": 1,
                "state": "finished",
                "category": category,
                "run_status": str((record or {}).get("run_status", "infrastructure_failed")),
            }
            if failure is not None:
                outcome["error_type"] = type(failure).__name__
            self.checkpoint.record_outcome(lane, outcome)
            self._cleanup_if_paired(entry.task, prepared)
            if category == "quota":
                return RunSummary(launched=launched, stop_reason="quota")
        return RunSummary(launched=launched, stop_reason=None)


def _patch_path(lane_dir: Path) -> Path:
    direct = lane_dir / "model.patch"
    return direct if direct.exists() else lane_dir / "runtime" / "model.patch"


def _patch_bytes(lane_dir: Path) -> bytes:
    patch = _patch_path(lane_dir)
    try:
        return patch.read_bytes()
    except FileNotFoundError:
        raise CampaignError(f"attempt lacks a durable patch artifact: {lane_dir}") from None


def export_predictions(
    root: str | Path,
    condition: str,
    destination: str | Path,
    *,
    auth_markers: Sequence[bytes] = (),
    model_name: str = "Marginal + Codex",
) -> None:
    """Create an immutable public prediction file containing no run outcomes or private data."""

    if condition not in {"baseline", "marginal"}:
        raise CampaignError("condition must be baseline or marginal")
    markers = tuple(marker for marker in auth_markers if len(marker) >= 16)
    records: list[dict[str, str]] = []
    for task in Campaign.open(root).tasks:
        lane = CampaignCheckpoint(Path(root)).lane_dir(task, condition)
        if not lane.is_dir():
            raise CampaignError(
                f"cannot export an unattempted lane: {task.instance_id}/{condition}"
            )
        patch = _patch_bytes(lane)
        if any(marker in patch for marker in markers):
            raise CampaignError("authentication material detected in exportable patch")
        records.append(
            {
                "instance_id": task.instance_id,
                "model_patch": patch.decode("utf-8", errors="surrogateescape"),
                "model_name_or_path": model_name,
            }
        )
    output = Path(destination)
    if output.exists():
        raise CampaignError("export destination already exists")
    output.parent.mkdir(parents=True, exist_ok=True)
    payload = "".join(json.dumps(item, sort_keys=True) + "\n" for item in records).encode("utf-8")
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{output.name}.", dir=output.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(temporary, 0o644)
        try:
            os.link(temporary, output)
        except FileExistsError as exc:
            raise CampaignError("export destination already exists") from exc
    finally:
        with contextlib.suppress(FileNotFoundError):
            temporary.unlink()


class JsonProblemProvider:
    """Read a local JSONL issue projection without loading any test/outcome fields."""

    def __init__(self, path: Path):
        self.problems: dict[str, dict[str, str]] = {}
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except OSError as exc:
            raise CampaignError("safe problem projection is unreadable") from exc
        for line in lines:
            try:
                value = json.loads(line)
            except json.JSONDecodeError as exc:
                raise CampaignError("safe problem projection is malformed") from exc
            if not isinstance(value, dict) or set(value) != {"instance_id", "problem_statement"}:
                raise CampaignError("safe problem projection contains a prohibited field")
            instance_id = value["instance_id"]
            statement = value["problem_statement"]
            if (
                not isinstance(instance_id, str)
                or not isinstance(statement, str)
                or instance_id in self.problems
            ):
                raise CampaignError("safe problem projection has invalid identities")
            self.problems[instance_id] = value

    def __call__(self, task: LiteTask) -> Mapping[str, str]:
        try:
            return self.problems[task.instance_id]
        except KeyError as exc:
            raise CampaignError(f"safe problem projection is missing {task.instance_id}") from exc


class DockerLiteRuntime:
    """Minimal Docker implementation; all commands are explicit and individually injectable."""

    def __init__(
        self,
        *,
        source_root: Path,
        auth_source: Path,
        marginal_commit: str,
        executor: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
    ):
        self.source_root = source_root.resolve()
        self.auth_source = auth_source.resolve()
        self.marginal_commit = marginal_commit
        self.executor = executor

    def _command(
        self, command: list[str], *, timeout: int = 1800
    ) -> subprocess.CompletedProcess[str]:
        try:
            return self.executor(
                command, check=False, capture_output=True, text=True, timeout=timeout
            )
        except (OSError, subprocess.SubprocessError) as exc:
            raise CampaignError(f"Docker infrastructure failure: {exc}") from exc

    def prepare(self, task: LiteTask) -> PreparedTask:
        pulled = self._command(["docker", "pull", task.official_image])
        if pulled.returncode != 0:
            raise CampaignError("Docker could not pull the official task image")
        digest = self._command(
            [
                "docker",
                "image",
                "inspect",
                "--format",
                "{{index .RepoDigests 0}}",
                task.official_image,
            ]
        )
        task_image = digest.stdout.strip()
        if digest.returncode != 0 or "@sha256:" not in task_image:
            raise CampaignError("Docker did not resolve an immutable official image digest")
        image_key = hashlib.sha256((task.instance_id + task_image).encode()).hexdigest()
        tag = f"marginal-lite-{image_key[:24]}"
        built = self._command(
            [
                "docker",
                "build",
                "--file",
                str(self.source_root / "benchmark/astra/lite/Dockerfile.solver"),
                "--build-arg",
                f"TASK_IMAGE={task_image}",
                "--build-arg",
                f"MARGINAL_SOURCE_COMMIT={self.marginal_commit}",
                "--tag",
                tag,
                str(self.source_root),
            ]
        )
        if built.returncode != 0:
            raise CampaignError("Docker could not build the task overlay")
        identity = self._command(["docker", "image", "inspect", "--format", "{{.Id}}", tag])
        if identity.returncode != 0 or not identity.stdout.strip().startswith("sha256:"):
            raise CampaignError("Docker did not resolve an immutable overlay image ID")
        return PreparedTask(task_image=task_image, overlay_image=identity.stdout.strip())

    def run_lane(
        self,
        task: LiteTask,
        condition: str,
        prepared: PreparedTask,
        lane_dir: Path,
        solver_input: str,
    ) -> Mapping[str, Any]:
        if not self.auth_source.is_file():
            raise CampaignError("Codex authentication source is unavailable")
        with tempfile.TemporaryDirectory(prefix="lite-input-") as temporary:
            prompt = Path(temporary) / "prompt.txt"
            prompt.write_text(solver_input, encoding="utf-8")
            command = [
                "docker",
                "run",
                "--rm",
                "--mount",
                f"type=bind,src={prompt},dst=/marginal-input/prompt.txt,readonly",
                "--mount",
                f"type=bind,src={lane_dir},dst=/marginal-output/attempt",
                "--mount",
                f"type=bind,src={self.auth_source},dst=/run/secrets/codex-auth.json,readonly",
                prepared.overlay_image,
                "--instance-id",
                task.instance_id,
                "--repo",
                task.repo,
                "--base-commit",
                task.base_commit,
                "--official-image",
                task.official_image,
                "--problem-hash",
                task.problem_hash,
                "--schedule-position",
                str(task.schedule_position),
                "--condition",
                condition,
            ]
            # LiteLaneConfig defaults are container paths; a dedicated subdirectory preserves the
            # immutable outer lane directory and its pre-launch marker.
            command.extend(["--run-dir", "/marginal-output/attempt/runtime"])
            completed = self._command(command, timeout=960)
        text = (completed.stdout + "\n" + completed.stderr).lower()
        if "quota" in text or "capacity" in text:
            return {"run_status": "quota_exhausted"}
        return {"run_status": "completed" if completed.returncode == 0 else "codex_failed"}

    def remove_image(self, image: str) -> None:
        self._command(["docker", "image", "rm", image], timeout=120)


def _auth_markers(path: Path) -> tuple[bytes, ...]:
    raw = path.read_bytes()
    markers: set[bytes] = {raw.strip()} if len(raw.strip()) >= 16 else set()
    try:
        value = json.loads(raw)
    except json.JSONDecodeError:
        value = None

    def collect(item: object) -> None:
        if isinstance(item, str) and len(item.encode()) >= 16:
            markers.add(item.encode())
        elif isinstance(item, dict):
            for child in item.values():
                collect(child)
        elif isinstance(item, list):
            for child in item:
                collect(child)

    collect(value)
    return tuple(markers)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    default_manifest = Path(__file__).resolve().parent / "lite" / "task-manifest.jsonl"
    init = commands.add_parser("init")
    init.add_argument("--campaign-dir", required=True, type=Path)
    init.add_argument("--manifest", type=Path, default=default_manifest)
    for name in ("next", "status"):
        command = commands.add_parser(name)
        command.add_argument("--campaign-dir", required=True, type=Path)
    run = commands.add_parser("run")
    run.add_argument("--campaign-dir", required=True, type=Path)
    run.add_argument("--max-lanes", required=True, type=int)
    run.add_argument("--problem-source", required=True, type=Path)
    run.add_argument("--auth", required=True, type=Path)
    run.add_argument("--source-root", type=Path, default=Path.cwd())
    run.add_argument("--marginal-commit", required=True)
    export = commands.add_parser("export")
    export.add_argument("--campaign-dir", required=True, type=Path)
    export.add_argument("--condition", required=True, choices=("baseline", "marginal"))
    export.add_argument("--output", required=True, type=Path)
    export.add_argument("--auth", required=True, type=Path)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.command == "init":
        initialize_campaign(args.campaign_dir, load_safe_manifest(args.manifest))
        print(json.dumps(Campaign.open(args.campaign_dir).status(), sort_keys=True))
    elif args.command == "next":
        entries = Campaign.open(args.campaign_dir).next_entries()
        if entries:
            print(
                json.dumps(
                    {"instance_id": entries[0].task.instance_id, "condition": entries[0].condition},
                    sort_keys=True,
                )
            )
        else:
            print(json.dumps({"next": None}))
    elif args.command == "status":
        print(json.dumps(Campaign.open(args.campaign_dir).status(), sort_keys=True))
    elif args.command == "run":
        runtime = DockerLiteRuntime(
            source_root=args.source_root,
            auth_source=args.auth,
            marginal_commit=args.marginal_commit,
        )
        result = CampaignRunner(
            args.campaign_dir, runtime, JsonProblemProvider(args.problem_source)
        ).run(max_lanes=args.max_lanes)
        print(json.dumps(asdict(result), sort_keys=True))
    else:
        export_predictions(
            args.campaign_dir, args.condition, args.output, auth_markers=_auth_markers(args.auth)
        )
        print(json.dumps({"output": str(args.output), "condition": args.condition}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
