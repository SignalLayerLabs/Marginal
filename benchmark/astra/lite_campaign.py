"""Resumable, immutable orchestrator for the paired SWE-bench Lite campaign.

The campaign checkpoint intentionally contains task identity and image provenance, never issue
text, benchmark test material, other-lane inputs, or authentication.  Docker and issue access
are dependency-injected so unit tests never need a daemon, a dataset, or Codex inference.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import tempfile
from collections.abc import Callable, Mapping, Sequence
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import Any, Protocol

from benchmark.astra.lite.checkpoint import (
    CampaignCheckpoint,
    CheckpointError,
    atomic_create_bytes,
    read_json,
)
from benchmark.astra.lite.freeze import CANONICAL_PROTOCOL, LiteTask, load_safe_manifest


class CampaignError(RuntimeError):
    """Raised when campaign integrity or the solver isolation boundary is violated."""


_FROZEN_MARGINAL_COMMIT = "71c8eae5ef1321c45c3d5c7aa8af1ffcded719b1"
FROZEN_PRODUCT_SUBTREE = "8b99ca79a11133117f538add2bf474851183de89"
FROZEN_PRODUCT_ARCHIVE_SHA256 = "2050e4cbe1b233633ed016637a687e4d674aa970338fe5fc24e480cb3e313bbd"


@dataclass(frozen=True, slots=True)
class SourceProvenance:
    commit: str
    tree: str
    product_commit: str = _FROZEN_MARGINAL_COMMIT
    product_tree: str = ""
    product_subtree: str = ""


def verify_frozen_source(
    source_root: Path,
    *,
    git_executor: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
) -> SourceProvenance:
    """Resolve a clean harness checkout and the exact frozen product Git object."""

    root = source_root.resolve()

    def git(*args: str) -> str:
        completed = git_executor(
            ["git", *args], cwd=root, check=False, capture_output=True, text=True, timeout=30
        )
        if completed.returncode != 0:
            raise CampaignError("frozen MARGINAL source cannot be resolved as a Git checkout")
        return completed.stdout.strip()

    expected = git("rev-parse", f"{_FROZEN_MARGINAL_COMMIT}^{{commit}}")
    actual = git("rev-parse", "HEAD^{commit}")
    if expected != _FROZEN_MARGINAL_COMMIT:
        raise CampaignError("frozen MARGINAL commit 71c8eae is unavailable")
    if git("status", "--porcelain"):
        raise CampaignError("frozen MARGINAL source checkout must be clean")
    tree = git("rev-parse", "HEAD^{tree}")
    if len(tree) != 40 or any(character not in "0123456789abcdef" for character in tree):
        raise CampaignError("frozen MARGINAL source tree is invalid")
    product_tree = git("rev-parse", f"{_FROZEN_MARGINAL_COMMIT}^{{tree}}")
    subtree = git("rev-parse", f"{_FROZEN_MARGINAL_COMMIT}:src/marginal")
    if subtree != FROZEN_PRODUCT_SUBTREE:
        raise CampaignError("frozen MARGINAL subtree identity mismatch")
    return SourceProvenance(
        commit=actual,
        tree=tree,
        product_commit=expected,
        product_tree=product_tree,
        product_subtree=subtree,
    )


@dataclass(frozen=True, slots=True)
class ScheduleEntry:
    task: LiteTask
    condition: str


@dataclass(frozen=True, slots=True)
class PreparedTask:
    """Digest-pinned task and locally-built overlay image identities."""

    task_image: str
    overlay_image: str
    baseline_image: str = ""
    marginal_image: str = ""
    source_commit: str = ""
    source_tree: str = ""
    product_commit: str = ""
    product_tree: str = ""
    product_subtree: str = ""
    product_archive_sha256: str = ""
    activation_mount_digest: str = ""
    prompt_sha256: str = ""

    def image_for(self, condition: str) -> str:
        if condition == "baseline":
            return self.baseline_image or self.overlay_image
        if condition == "marginal":
            return self.marginal_image or self.overlay_image
        raise CampaignError("condition must be baseline or marginal")


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
    if _prompt_sha256(template) != CANONICAL_PROTOCOL["prompt_sha256"]:
        raise CampaignError("frozen solver prompt SHA-256 does not match the protocol")
    if template.count("{{problem_statement}}") != 1:
        raise CampaignError("frozen solver prompt has an invalid issue placeholder")
    return template.replace("{{problem_statement}}", problem)


def _prompt_sha256(template: str) -> str:
    return hashlib.sha256(template.encode("utf-8")).hexdigest()


def frozen_prompt_sha256() -> str:
    path = Path(__file__).resolve().parents[1] / "prompt_template.txt"
    try:
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError as exc:
        raise CampaignError("frozen solver prompt is unreadable") from exc
    if digest != CANONICAL_PROTOCOL["prompt_sha256"]:
        raise CampaignError("frozen solver prompt SHA-256 does not match the protocol")
    return digest


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

    def next_tasks(self) -> tuple[LiteTask, ...]:
        return tuple(
            task
            for task in self.tasks
            if any(
                not self.checkpoint.has_attempt(task, condition)
                for condition in task.condition_order
            )
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


def _quota_signal(lane: Path, record: Mapping[str, Any] | None) -> bool:
    if "quota" in str((record or {}).get("run_status", "")).lower():
        return True
    for name in ("codex-stderr.log", "run-record.json"):
        candidate = lane / "runtime" / name
        try:
            text = candidate.read_text(encoding="utf-8", errors="replace").lower()
        except FileNotFoundError:
            continue
        if "quota" in text or "capacity exhausted" in text or "rate limit" in text:
            return True
    return False


def _outcome_category(
    lane: Path, record: Mapping[str, Any] | None, error: BaseException | None
) -> str:
    if error is not None:
        return "infrastructure"
    if _quota_signal(lane, record):
        return "quota"
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
        prepared = replace(prepared, prompt_sha256=frozen_prompt_sha256())
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
            (self.checkpoint.lane_dir(task, condition) / "model.patch").is_file()
            and (self.checkpoint.lane_dir(task, condition) / "outcome.json").is_file()
            for condition in task.condition_order
        ):
            return
        # Explicit identities only; never use a broad Docker prune operation.
        for image in dict.fromkeys(
            (
                prepared.baseline_image or prepared.overlay_image,
                prepared.marginal_image or prepared.overlay_image,
            )
        ):
            self.runtime.remove_image(image)
        self.runtime.remove_image(prepared.task_image)

    def run(self, *, max_lanes: int) -> RunSummary:
        if max_lanes <= 0:
            raise CampaignError("max_lanes must be positive")
        launched = 0
        with self.checkpoint.campaign_lock():
            campaign = Campaign(self.checkpoint)
            for entry in campaign.entries():
                lane = self.checkpoint.lane_dir(entry.task, entry.condition)
                if lane.is_dir() and not (lane / "outcome.json").exists():
                    self.checkpoint.record_outcome(
                        lane,
                        {
                            "schema_version": 3,
                            "state": "uncertain_interrupted",
                            "category": "infrastructure",
                            "run_status": "uncertain",
                        },
                    )
            for entry in campaign.next_entries():
                if launched >= max_lanes:
                    break
                try:
                    prepared = self._prepared(entry.task)
                    solver_input = render_solver_input(
                        entry.task, self.problem_provider(entry.task)
                    )
                except Exception as exc:
                    self.checkpoint.record_prelaunch_failure(entry.task, exc)
                    return RunSummary(launched=launched, stop_reason="infrastructure")
                lane = self.checkpoint.claim_attempt(entry.task, entry.condition, asdict(prepared))
                if lane is None:
                    continue
                atomic_create_bytes(lane / "model.patch", b"")
                launched += 1
                record: Mapping[str, Any] | None = None
                failure: BaseException | None = None
                try:
                    record = self.runtime.run_lane(
                        entry.task, entry.condition, prepared, lane, solver_input
                    )
                except Exception as exc:
                    failure = exc
                category = _outcome_category(lane, record, failure)
                outcome: dict[str, Any] = {
                    "schema_version": 3,
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
    runtime = lane_dir / "runtime" / "model.patch"
    return runtime if runtime.exists() else lane_dir / "model.patch"


def _patch_bytes(lane_dir: Path) -> bytes:
    patch = _patch_path(lane_dir)
    try:
        return patch.read_bytes()
    except FileNotFoundError:
        raise CampaignError(f"attempt lacks a durable patch artifact: {lane_dir}") from None


PUBLIC_ARTIFACT_ALLOWLIST = frozenset({"predictions"})


def validate_public_artifacts(
    artifacts: Mapping[str, bytes], *, auth_markers: Sequence[bytes] = ()
) -> None:
    """Fail closed before durable publication of any allowlisted public payload.

    Public formats are deliberately enumerated here.  New trajectories or provenance exports
    must join this allowlist and call this function before they become materialized artifacts.
    """

    if not artifacts or not set(artifacts).issubset(PUBLIC_ARTIFACT_ALLOWLIST):
        raise CampaignError("public artifact is not in the explicit export allowlist")
    markers = tuple(marker for marker in auth_markers if marker)
    if len(markers) != len(tuple(auth_markers)) or any(
        not isinstance(marker, bytes) for marker in markers
    ):
        raise CampaignError("public artifact authentication markers are invalid")
    for name, payload in artifacts.items():
        if not isinstance(payload, bytes):
            raise CampaignError(f"public artifact payload is unreadable: {name}")
        if any(marker in payload for marker in markers):
            raise CampaignError("authentication material detected in public artifact")


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
    markers = tuple(auth_markers)
    records: list[dict[str, str]] = []
    for task in Campaign.open(root).tasks:
        lane = CampaignCheckpoint(Path(root)).lane_dir(task, condition)
        if not lane.is_dir():
            raise CampaignError(
                f"cannot export an unattempted lane: {task.instance_id}/{condition}"
            )
        patch = _patch_bytes(lane)
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
    payload = "".join(json.dumps(item, sort_keys=True) + "\n" for item in records).encode("utf-8")
    validate_public_artifacts({"predictions": payload}, auth_markers=markers)
    try:
        atomic_create_bytes(output, payload, mode=0o644)
    except CheckpointError as exc:
        raise CampaignError("export destination already exists or cannot be published") from exc


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
        exchange_root: Path | None = None,
        executor: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
        git_executor: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
    ):
        self.source_root = source_root.resolve()
        self.auth_source = auth_source.resolve()
        self.exchange_root = (exchange_root or Path(tempfile.gettempdir())).resolve()
        self.executor = executor
        self.git_executor = git_executor
        self._product_archive: Path | None = None

    def __enter__(self) -> DockerLiteRuntime:
        return self

    def __exit__(self, *_exc: object) -> None:
        self.close()

    def close(self) -> None:
        if self._product_archive is not None:
            self._product_archive.unlink(missing_ok=True)
            self._product_archive = None

    def _ensure_exchange_root(self) -> None:
        try:
            self.exchange_root.mkdir(parents=True)
        except FileExistsError:
            if not self.exchange_root.is_dir():
                raise CampaignError("runtime exchange root is not a directory") from None
        else:
            self.exchange_root.chmod(0o700)

    def _product_tar(self, source: SourceProvenance) -> Path:
        if self._product_archive is not None:
            self.validate_frozen_product_archive(self._product_archive)
            return self._product_archive
        self._ensure_exchange_root()
        descriptor, name = tempfile.mkstemp(
            prefix="lite-frozen-product-", suffix=".tar", dir=self.exchange_root
        )
        target = Path(name)
        archive = self.git_executor(
            ["git", "archive", "--format=tar", source.product_commit, "src/marginal"],
            cwd=self.source_root,
            check=False,
            capture_output=True,
            text=False,
            timeout=30,
        )
        if archive.returncode != 0:
            os.close(descriptor)
            target.unlink(missing_ok=True)
            raise CampaignError("could not extract frozen MARGINAL product Git object")
        payload = archive.stdout
        if isinstance(payload, str):
            # Enables a simple injected Git fixture without weakening byte verification.
            payload = payload.encode("utf-8")
        try:
            with os.fdopen(descriptor, "wb") as output:
                output.write(payload)
                output.flush()
                os.fsync(output.fileno())
            target.chmod(0o444)
            self.validate_frozen_product_archive(target)
        except BaseException:
            target.unlink(missing_ok=True)
            raise
        self._product_archive = target
        return target

    @staticmethod
    def validate_frozen_product_archive(path: Path) -> None:
        try:
            payload = path.read_bytes()
        except OSError as exc:
            raise CampaignError("frozen product archive is unreadable") from exc
        if hashlib.sha256(payload).hexdigest() != FROZEN_PRODUCT_ARCHIVE_SHA256:
            raise CampaignError("frozen product archive digest mismatch")

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
        source = verify_frozen_source(self.source_root, git_executor=self.git_executor)
        self._product_tar(source)
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

        runtime_tag = f"{tag}-shared"
        built = self._command(
            [
                "docker",
                "build",
                "--file",
                str(self.source_root / "benchmark/astra/lite/Dockerfile.solver"),
                "--target",
                "baseline",
                "--build-arg",
                f"TASK_IMAGE={task_image}",
                "--build-arg",
                f"MARGINAL_SOURCE_COMMIT={source.commit}",
                "--tag",
                runtime_tag,
                str(self.source_root),
            ]
        )
        if built.returncode != 0:
            raise CampaignError("Docker could not build the shared task runtime")
        identity = self._command(["docker", "image", "inspect", "--format", "{{.Id}}", runtime_tag])
        if identity.returncode != 0 or not identity.stdout.strip().startswith("sha256:"):
            raise CampaignError("Docker did not resolve an immutable shared image ID")
        shared = identity.stdout.strip()
        return PreparedTask(
            task_image=task_image,
            overlay_image=shared,
            baseline_image=shared,
            marginal_image=shared,
            source_commit=source.commit,
            source_tree=source.tree,
            product_commit=source.product_commit,
            product_tree=source.product_tree,
            product_subtree=source.product_subtree,
            product_archive_sha256=FROZEN_PRODUCT_ARCHIVE_SHA256,
            activation_mount_digest=FROZEN_PRODUCT_ARCHIVE_SHA256,
        )

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
        self._ensure_exchange_root()
        with tempfile.TemporaryDirectory(prefix="lite-input-", dir=self.exchange_root) as temporary:
            prompt = Path(temporary) / "prompt.txt"
            prompt.write_text(solver_input, encoding="utf-8")
            command = [
                "docker",
                "run",
                "--rm",
                "--cap-add",
                "SYS_ADMIN",
                "--security-opt",
                "seccomp=unconfined",
                "--security-opt",
                "apparmor=unconfined",
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
            if condition == "marginal":
                product = self._product_tar(
                    SourceProvenance(
                        prepared.source_commit,
                        prepared.source_tree,
                        prepared.product_commit,
                        prepared.product_tree,
                        prepared.product_subtree,
                    )
                )
                self.validate_frozen_product_archive(product)
                command[3:3] = [
                    "--mount",
                    f"type=bind,src={product},dst=/opt/marginal-product/marginal.tar,readonly",
                ]
            # LiteLaneConfig defaults are container paths; a dedicated subdirectory preserves the
            # immutable outer lane directory and its pre-launch marker.
            command.extend(["--run-dir", "/marginal-output/attempt/runtime"])
            if condition == "marginal":
                command.extend(
                    [
                        "--marginal-product-archive",
                        "/opt/marginal-product/marginal.tar",
                        "--marginal-product-sha256",
                        FROZEN_PRODUCT_ARCHIVE_SHA256,
                    ]
                )
            completed = self._command(command, timeout=960)
        atomic_create_bytes(lane_dir / "docker.stdout.log", completed.stdout.encode("utf-8"))
        atomic_create_bytes(lane_dir / "docker.stderr.log", completed.stderr.encode("utf-8"))
        text = (completed.stdout + "\n" + completed.stderr).lower()
        record_path = lane_dir / "runtime" / "run-record.json"
        inner_record: dict[str, Any] | None = None
        if record_path.is_file():
            try:
                loaded = json.loads(record_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                return {
                    "run_status": "infrastructure_failed",
                    "error_code": "INVALID_RUN_RECORD",
                }
            if not isinstance(loaded, dict) or not isinstance(loaded.get("run_status"), str):
                return {
                    "run_status": "infrastructure_failed",
                    "error_code": "INVALID_RUN_RECORD",
                }
            inner_record = loaded
        if "quota" in text or "capacity" in text or _quota_signal(lane_dir, inner_record):
            return {"run_status": "quota_exhausted"}
        events_path = lane_dir / "runtime" / "codex-events.jsonl"
        try:
            events_text = events_path.read_text(encoding="utf-8", errors="replace").lower()
        except FileNotFoundError:
            events_text = ""
        if any(
            marker in events_text
            for marker in (
                "bwrap: no permissions",
                "failed to create a new namespace",
                "bwrap: failed to make / slave",
            )
        ):
            return {"run_status": "infrastructure_failed", "error_code": "SANDBOX_UNAVAILABLE"}
        if completed.returncode != 0 or inner_record is None:
            return {
                "run_status": "infrastructure_failed",
                "docker_exit_code": completed.returncode,
            }
        return inner_record

    def remove_image(self, image: str) -> None:
        removed = self._command(["docker", "image", "rm", image], timeout=120)
        if removed.returncode != 0:
            raise CampaignError(f"Docker could not remove explicit image: {image}")


def _auth_markers(path: Path) -> tuple[bytes, ...]:
    try:
        raw = path.read_bytes()
        value = json.loads(raw)
    except (OSError, json.JSONDecodeError) as exc:
        raise CampaignError("authentication material is unreadable or unparseable") from exc
    markers: set[bytes] = set()

    def collect(item: object) -> None:
        if isinstance(item, str) and item:
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
        with DockerLiteRuntime(
            source_root=args.source_root,
            auth_source=args.auth,
            exchange_root=args.campaign_dir / ".runtime-exchange",
        ) as runtime:
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
