"""Atomic, append-only state for the SWE-bench Lite paired campaign."""

from __future__ import annotations

import contextlib
import hashlib
import json
import os
import tempfile
from dataclasses import asdict
from pathlib import Path
from typing import Any

from .freeze import LiteTask


class CheckpointError(RuntimeError):
    """Raised when immutable campaign state is absent, malformed, or conflicts."""


def _canonical(value: object) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def atomic_create_bytes(path: Path, payload: bytes, *, mode: int = 0o600) -> None:
    """Create one durable byte stream without ever replacing an existing file."""

    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as output:
            output.write(payload)
            output.flush()
            os.fsync(output.fileno())
        os.chmod(temporary, mode)
        try:
            os.link(temporary, path)
        except FileExistsError as exc:
            raise CheckpointError(f"immutable checkpoint already exists: {path}") from exc
        directory = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        with contextlib.suppress(FileNotFoundError):
            temporary.unlink()


def atomic_create_json(path: Path, value: object) -> None:
    """Create one JSON document without ever replacing an existing document."""

    atomic_create_bytes(path, _canonical(value))


def read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise CheckpointError(f"invalid checkpoint: {path}") from exc
    if not isinstance(value, dict):
        raise CheckpointError(f"checkpoint must be an object: {path}")
    return value


class CampaignCheckpoint:
    """Immutable campaign schedule and lane-directory record store."""

    def __init__(self, root: Path):
        self.root = root.resolve()

    @property
    def campaign_path(self) -> Path:
        return self.root / "campaign.json"

    @property
    def schedule_path(self) -> Path:
        return self.root / "schedule.jsonl"

    def initialize(self, tasks: tuple[LiteTask, ...]) -> None:
        if os.name != "posix":
            raise CheckpointError("Lite campaign checkpoints require a POSIX host")
        if not tasks:
            raise CheckpointError("campaign schedule must not be empty")
        if [task.schedule_position for task in tasks] != list(range(len(tasks))):
            raise CheckpointError("tasks must retain contiguous frozen schedule positions")
        if len({task.instance_id for task in tasks}) != len(tasks):
            raise CheckpointError("campaign schedule has duplicate instance IDs")
        if any(set(task.condition_order) != {"baseline", "marginal"} for task in tasks):
            raise CheckpointError("each task must pair baseline and marginal exactly once")
        self.root.mkdir(parents=True, exist_ok=True)
        os.chmod(self.root, 0o700)
        schedule = b"".join(_canonical(asdict(task)) for task in tasks)
        digest = hashlib.sha256(schedule).hexdigest()
        if self.campaign_path.exists() or self.schedule_path.exists():
            if not self.campaign_path.is_file() or not self.schedule_path.is_file():
                raise CheckpointError("campaign checkpoint is incomplete")
            metadata = read_json(self.campaign_path)
            if (
                metadata.get("schedule_sha256") != digest
                or self.schedule_path.read_bytes() != schedule
            ):
                raise CheckpointError("campaign is already initialized with a different schedule")
            return
        atomic_create_bytes(self.schedule_path, schedule)
        try:
            atomic_create_json(
                self.campaign_path,
                {"schema_version": 1, "schedule_sha256": digest, "task_count": len(tasks)},
            )
        except Exception:
            # A lone schedule is intentionally not silently reused: it is ambiguous after a crash.
            raise

    def tasks(self) -> tuple[LiteTask, ...]:
        metadata = read_json(self.campaign_path)
        try:
            schedule = self.schedule_path.read_bytes()
        except OSError as exc:
            raise CheckpointError("campaign schedule is missing") from exc
        if hashlib.sha256(schedule).hexdigest() != metadata.get("schedule_sha256"):
            raise CheckpointError("campaign schedule digest does not match its checkpoint")
        rows: list[LiteTask] = []
        for line in schedule.splitlines():
            try:
                value = json.loads(line)
                if not isinstance(value, dict):
                    raise ValueError
                value["condition_order"] = tuple(value["condition_order"])
                rows.append(LiteTask(**value))
            except (TypeError, ValueError, json.JSONDecodeError, KeyError) as exc:
                raise CheckpointError("campaign schedule is malformed") from exc
        return tuple(rows)

    @staticmethod
    def task_key(task: LiteTask) -> str:
        return f"{task.schedule_position:04d}-{task.instance_id}"

    def lane_dir(self, task: LiteTask, condition: str) -> Path:
        if condition not in task.condition_order:
            raise CheckpointError("condition is not scheduled for this task")
        return self.root / "lanes" / self.task_key(task) / condition

    def lease_dir(self, task: LiteTask) -> Path:
        return self.root / "leases" / self.task_key(task)

    def has_lease(self, task: LiteTask) -> bool:
        return self.lease_dir(task).exists()

    def claim_task(self, task: LiteTask) -> bool:
        """Atomically claim the complete ordered pair; a stale lease is never reusable."""

        lease = self.lease_dir(task)
        lease.parent.mkdir(parents=True, exist_ok=True)
        try:
            lease.mkdir()
        except FileExistsError:
            return False
        os.chmod(lease, 0o700)
        atomic_create_json(
            lease / "lease.json",
            {
                "schema_version": 2,
                "state": "leased",
                "instance_id": task.instance_id,
                "schedule_position": task.schedule_position,
            },
        )
        return True

    def has_attempt(self, task: LiteTask, condition: str) -> bool:
        return self.lane_dir(task, condition).exists()

    def claim_attempt(
        self, task: LiteTask, condition: str, prepared: dict[str, str]
    ) -> Path | None:
        lane = self.lane_dir(task, condition)
        lane.parent.mkdir(parents=True, exist_ok=True)
        try:
            lane.mkdir()
        except FileExistsError:
            # A directory without a marker is uncertain after a crash; do not launch it again.
            return None
        os.chmod(lane, 0o700)
        atomic_create_json(
            lane / "attempt.json",
            {
                "schema_version": 1,
                "state": "started",
                "instance_id": task.instance_id,
                "condition": condition,
                "schedule_position": task.schedule_position,
                "task_image": prepared["task_image"],
                "overlay_image": prepared["overlay_image"],
                "runtime_image": prepared[
                    "baseline_image" if condition == "baseline" else "marginal_image"
                ]
                or prepared["overlay_image"],
                "source_commit": prepared["source_commit"],
                "source_tree": prepared["source_tree"],
                "prompt_sha256": prepared["prompt_sha256"],
            },
        )
        return lane

    def stage_pair(self, task: LiteTask, prepared: dict[str, str]) -> tuple[Path, Path]:
        """Create both pre-launch records and exportable empty patches under the task lease."""

        if not self.has_lease(task):
            raise CheckpointError("cannot stage a task without its immutable lease")
        lanes: list[Path] = []
        for condition in task.condition_order:
            lane = self.claim_attempt(task, condition, prepared)
            if lane is None:
                raise CheckpointError("a task lease has an existing or uncertain lane")
            atomic_create_bytes(lane / "model.patch", b"")
            lanes.append(lane)
        return lanes[0], lanes[1]

    def task_record_path(self, task: LiteTask) -> Path:
        return self.root / "tasks" / f"{self.task_key(task)}.json"

    def read_prepared(self, task: LiteTask) -> dict[str, str] | None:
        path = self.task_record_path(task)
        if not path.exists():
            return None
        value = read_json(path)
        expected = {
            "schema_version",
            "instance_id",
            "task_image",
            "overlay_image",
            "baseline_image",
            "marginal_image",
            "source_commit",
            "source_tree",
            "prompt_sha256",
        }
        if set(value) != expected:
            raise CheckpointError("prepared task record contains unsafe or missing fields")
        if value["instance_id"] != task.instance_id:
            raise CheckpointError("prepared task record identity mismatch")
        image_keys = ("task_image", "overlay_image", "baseline_image", "marginal_image")
        provenance_keys = ("source_commit", "source_tree", "prompt_sha256")
        if not all(isinstance(value[key], str) for key in (*image_keys, *provenance_keys)):
            raise CheckpointError("prepared task record has invalid image identity")
        if not value["task_image"] or not value["overlay_image"]:
            raise CheckpointError("prepared task record has invalid image identity")
        return {key: value[key] for key in expected if key not in {"schema_version", "instance_id"}}

    def record_prepared(self, task: LiteTask, prepared: dict[str, str]) -> None:
        expected = {
            "task_image",
            "overlay_image",
            "baseline_image",
            "marginal_image",
            "source_commit",
            "source_tree",
            "prompt_sha256",
        }
        if set(prepared) != expected or not all(
            isinstance(value, str) for value in prepared.values()
        ):
            raise CheckpointError("prepared image record is invalid")
        atomic_create_json(
            self.task_record_path(task),
            {"schema_version": 1, "instance_id": task.instance_id, **prepared},
        )

    def record_outcome(self, lane: Path, outcome: dict[str, Any]) -> None:
        atomic_create_json(lane / "outcome.json", outcome)
