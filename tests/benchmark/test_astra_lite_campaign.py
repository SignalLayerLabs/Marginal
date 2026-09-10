from __future__ import annotations

import hashlib
import json
import subprocess
from dataclasses import dataclass
from pathlib import Path

import pytest
from benchmark.astra.lite.freeze import LiteTask


def _task(position: int, instance_id: str, order: tuple[str, str]) -> LiteTask:
    return LiteTask(
        instance_id=instance_id,
        repo="django/django",
        base_commit="a" * 40,
        official_image=f"example/{instance_id}:latest",
        problem_hash=hashlib.sha256(f"Issue {instance_id}".encode()).hexdigest(),
        schedule_position=position,
        condition_order=order,
    )


@dataclass
class FakeRuntime:
    launched: list[tuple[str, str, str]]
    removed: list[str]
    quota_after: tuple[str, str] | None = None

    def prepare(self, task: LiteTask):
        from benchmark.astra.lite_campaign import PreparedTask

        return PreparedTask(
            task_image=f"example/{task.instance_id}@sha256:{'b' * 64}",
            overlay_image=f"local/{task.instance_id}@sha256:{'c' * 64}",
        )

    def run_lane(self, task, condition, prepared, lane_dir, solver_input):
        self.launched.append((task.instance_id, condition, prepared.overlay_image))
        (lane_dir / "model.patch").write_text("diff --git a/a b/a\n", encoding="utf-8")
        if self.quota_after == (task.instance_id, condition):
            return {"run_status": "quota_exhausted"}
        return {"run_status": "completed"}

    def remove_image(self, image: str) -> None:
        self.removed.append(image)


def _provider(task: LiteTask) -> dict[str, str]:
    return {"instance_id": task.instance_id, "problem_statement": f"Issue {task.instance_id}"}


def test_init_persists_the_given_schedule_order_without_reordering(tmp_path: Path) -> None:
    from benchmark.astra.lite_campaign import Campaign, initialize_campaign

    tasks = (
        _task(0, "b__b-2", ("marginal", "baseline")),
        _task(1, "a__a-1", ("baseline", "marginal")),
    )
    initialize_campaign(tmp_path, tasks)

    campaign = Campaign.open(tmp_path)
    assert [(item.task.instance_id, item.condition) for item in campaign.next_entries()] == [
        ("b__b-2", "marginal"),
        ("b__b-2", "baseline"),
        ("a__a-1", "baseline"),
        ("a__a-1", "marginal"),
    ]


def test_run_writes_an_attempt_marker_before_a_lane_can_launch(tmp_path: Path) -> None:
    from benchmark.astra.lite_campaign import CampaignRunner, initialize_campaign

    task = _task(0, "django__django-11099", ("baseline", "marginal"))
    initialize_campaign(tmp_path, (task,))
    FakeRuntime([], [])

    class InspectingRuntime(FakeRuntime):
        def run_lane(self, task, condition, prepared, lane_dir, solver_input):
            assert (
                json.loads((lane_dir / "attempt.json").read_text(encoding="utf-8"))["state"]
                == "started"
            )
            return super().run_lane(task, condition, prepared, lane_dir, solver_input)

    result = CampaignRunner(tmp_path, InspectingRuntime([], []), _provider).run(max_lanes=2)

    assert result.launched == 2
    assert (
        tmp_path / "lanes" / "0000-django__django-11099" / "baseline" / "attempt.json"
    ).is_file()


def test_run_refuses_to_split_a_paired_task_at_a_one_lane_limit(tmp_path: Path) -> None:
    from benchmark.astra.lite_campaign import CampaignError, CampaignRunner, initialize_campaign

    task = _task(0, "django__django-11099", ("baseline", "marginal"))
    initialize_campaign(tmp_path, (task,))
    with pytest.raises(CampaignError, match="complete paired task"):
        CampaignRunner(tmp_path, FakeRuntime([], []), _provider).run(max_lanes=1)


def test_quota_stop_preserves_attempt_and_stops_before_next_lane(tmp_path: Path) -> None:
    from benchmark.astra.lite_campaign import CampaignRunner, initialize_campaign

    task = _task(0, "django__django-11099", ("baseline", "marginal"))
    initialize_campaign(tmp_path, (task,))
    runtime = FakeRuntime([], [], quota_after=(task.instance_id, "baseline"))

    result = CampaignRunner(tmp_path, runtime, _provider).run(max_lanes=2)

    assert result.stop_reason == "quota"
    assert [item[:2] for item in runtime.launched] == [(task.instance_id, "baseline")]
    outcome = json.loads(
        (tmp_path / "lanes" / "0000-django__django-11099" / "baseline" / "outcome.json").read_text()
    )
    assert outcome["category"] == "quota"


def test_lane_failure_preserves_an_empty_patch_for_later_export(tmp_path: Path) -> None:
    from benchmark.astra.lite_campaign import CampaignRunner, initialize_campaign

    task = _task(0, "django__django-11099", ("baseline", "marginal"))
    initialize_campaign(tmp_path, (task,))

    class FailingRuntime(FakeRuntime):
        def run_lane(self, task, condition, prepared, lane_dir, solver_input):
            raise RuntimeError("fixture Docker failure")

    CampaignRunner(tmp_path, FailingRuntime([], []), _provider).run(max_lanes=2)

    lane = tmp_path / "lanes" / "0000-django__django-11099" / "baseline"
    assert (lane / "model.patch").read_bytes() == b""
    assert json.loads((lane / "outcome.json").read_text())["category"] == "infrastructure"


def test_off_on_pair_uses_one_prepared_overlay_then_removes_only_explicit_images(
    tmp_path: Path,
) -> None:
    from benchmark.astra.lite_campaign import CampaignRunner, initialize_campaign

    task = _task(0, "django__django-11099", ("marginal", "baseline"))
    initialize_campaign(tmp_path, (task,))
    runtime = FakeRuntime([], [])

    CampaignRunner(tmp_path, runtime, _provider).run(max_lanes=2)

    assert [item[1] for item in runtime.launched] == ["marginal", "baseline"]
    assert len({item[2] for item in runtime.launched}) == 1
    assert runtime.removed == [
        f"local/{task.instance_id}@sha256:{'c' * 64}",
        f"example/{task.instance_id}@sha256:{'b' * 64}",
    ]


def test_problem_projection_must_be_safe_and_match_the_frozen_hash(tmp_path: Path) -> None:
    from benchmark.astra.lite_campaign import CampaignError, render_solver_input

    task = _task(0, "django__django-11099", ("baseline", "marginal"))
    assert "Issue django__django-11099" in render_solver_input(task, _provider(task))
    with pytest.raises(CampaignError, match="allowlisted"):
        render_solver_input(task, {**_provider(task), "hints": "forbidden"})
    with pytest.raises(CampaignError, match="hash"):
        render_solver_input(task, {"instance_id": task.instance_id, "problem_statement": "changed"})


def test_export_rejects_auth_markers_and_does_not_export_outcome_data(tmp_path: Path) -> None:
    from benchmark.astra.lite_campaign import (
        CampaignError,
        CampaignRunner,
        export_predictions,
        initialize_campaign,
    )

    task = _task(0, "django__django-11099", ("baseline", "marginal"))
    initialize_campaign(tmp_path, (task,))
    runtime = FakeRuntime([], [])
    CampaignRunner(tmp_path, runtime, _provider).run(max_lanes=2)

    destination = tmp_path / "baseline.jsonl"
    export_predictions(tmp_path, "baseline", destination, auth_markers=(b"secret-marker-123456",))
    exported = json.loads(destination.read_text(encoding="utf-8"))
    assert set(exported) == {"instance_id", "model_patch", "model_name_or_path"}
    assert "completed" not in destination.read_text(encoding="utf-8")

    destination.unlink()
    patch = tmp_path / "lanes" / "0000-django__django-11099" / "baseline" / "model.patch"
    patch.write_bytes(b"secret-marker-123456")
    with pytest.raises(CampaignError, match="authentication"):
        export_predictions(
            tmp_path, "baseline", destination, auth_markers=(b"secret-marker-123456",)
        )


def test_solver_entrypoint_accepts_a_child_runtime_directory_for_immutable_attempts() -> None:
    from benchmark.astra.lite_lane import _parser

    args = _parser().parse_args(
        [
            "--instance-id",
            "django__django-11099",
            "--repo",
            "django/django",
            "--base-commit",
            "a" * 40,
            "--official-image",
            "swebench/sweb.eval.x86_64.django_1776_django-11099:latest",
            "--problem-hash",
            "b" * 64,
            "--schedule-position",
            "0",
            "--condition",
            "baseline",
            "--run-dir",
            "/marginal-output/attempt/runtime",
        ]
    )

    assert args.run_dir == Path("/marginal-output/attempt/runtime")


def test_docker_runtime_is_injectable_and_uses_only_explicit_image_operations(
    tmp_path: Path,
) -> None:
    from benchmark.astra.lite_campaign import DockerLiteRuntime

    task = _task(0, "django__django-11099", ("baseline", "marginal"))
    commands: list[list[str]] = []

    def fake_docker(command, **_kwargs):
        commands.append(command)
        if command[:2] == ["docker", "pull"]:
            return subprocess.CompletedProcess(command, 0, "", "")
        if command[-1] == task.official_image:
            return subprocess.CompletedProcess(
                command, 0, f"example/{task.instance_id}@sha256:{'b' * 64}\n", ""
            )
        if command[:3] == ["docker", "image", "inspect"]:
            suffix = "c" if command[-1].endswith("baseline") else "d"
            return subprocess.CompletedProcess(command, 0, f"sha256:{suffix * 64}\n", "")
        return subprocess.CompletedProcess(command, 0, "", "")

    auth = tmp_path / "auth.json"
    auth.write_text("{}\n", encoding="utf-8")

    def fake_git(command, **_kwargs):
        if command[-2:] == ["status", "--porcelain"]:
            return subprocess.CompletedProcess(command, 0, "", "")
        if command[-1].endswith("^{commit}"):
            return subprocess.CompletedProcess(
                command, 0, "71c8eae5ef1321c45c3d5c7aa8af1ffcded719b1\n", ""
            )
        return subprocess.CompletedProcess(
            command, 0, "51c22b9eec66b08bfa58ac8bad89bd964aaafd39\n", ""
        )

    runtime = DockerLiteRuntime(
        source_root=Path(__file__).resolve().parents[2],
        auth_source=auth,
        executor=fake_docker,
        git_executor=fake_git,
    )

    prepared = runtime.prepare(task)
    runtime.remove_image(prepared.overlay_image)
    runtime.remove_image(prepared.task_image)

    assert prepared.task_image == f"example/{task.instance_id}@sha256:{'b' * 64}"
    assert prepared.baseline_image == f"sha256:{'c' * 64}"
    assert prepared.marginal_image == prepared.overlay_image == f"sha256:{'d' * 64}"
    assert [command[:3] for command in commands] == [
        ["docker", "pull", task.official_image],
        ["docker", "image", "inspect"],
        ["docker", "build", "--file"],
        ["docker", "image", "inspect"],
        ["docker", "build", "--file"],
        ["docker", "image", "inspect"],
        ["docker", "image", "rm"],
        ["docker", "image", "rm"],
    ]
    assert not any("prune" in command for command in commands)


def test_changed_frozen_prompt_is_rejected_before_solver_input_is_rendered(tmp_path: Path) -> None:
    from benchmark.astra.lite_campaign import CampaignError, render_solver_input

    task = _task(0, "django__django-11099", ("baseline", "marginal"))
    prompt = tmp_path / "prompt.txt"
    prompt.write_text("ISSUE: {{problem_statement}}\n", encoding="utf-8")

    with pytest.raises(CampaignError, match="prompt SHA-256"):
        render_solver_input(task, _provider(task), prompt_path=prompt)


def test_task_lease_stages_empty_patches_before_an_abrupt_exit_and_blocks_sibling(
    tmp_path: Path,
) -> None:
    from benchmark.astra.lite_campaign import CampaignRunner, initialize_campaign

    task = _task(0, "django__django-11099", ("baseline", "marginal"))
    initialize_campaign(tmp_path, (task,))

    class ExitingRuntime(FakeRuntime):
        def run_lane(self, task, condition, prepared, lane_dir, solver_input):
            self.launched.append((task.instance_id, condition, prepared.overlay_image))
            raise SystemExit(75)

    exiting = ExitingRuntime([], [])
    with pytest.raises(SystemExit):
        CampaignRunner(tmp_path, exiting, _provider).run(max_lanes=2)

    root = tmp_path / "lanes" / "0000-django__django-11099"
    assert (root / "baseline" / "model.patch").read_bytes() == b""
    assert (root / "marginal" / "model.patch").read_bytes() == b""
    sibling = FakeRuntime([], [])
    assert CampaignRunner(tmp_path, sibling, _provider).run(max_lanes=2).launched == 0
    assert sibling.launched == []
    assert exiting.removed == []


def test_stderr_only_quota_signal_stops_before_the_next_task_is_claimed(tmp_path: Path) -> None:
    from benchmark.astra.lite_campaign import CampaignRunner, initialize_campaign

    first = _task(0, "django__django-11099", ("baseline", "marginal"))
    second = _task(1, "sympy__sympy-12419", ("baseline", "marginal"))
    initialize_campaign(tmp_path, (first, second))

    class StderrQuotaRuntime(FakeRuntime):
        def run_lane(self, task, condition, prepared, lane_dir, solver_input):
            self.launched.append((task.instance_id, condition, prepared.overlay_image))
            runtime = lane_dir / "runtime"
            runtime.mkdir()
            (runtime / "codex-stderr.log").write_text("account capacity exhausted\n")
            return {"run_status": "codex_failed"}

    runtime = StderrQuotaRuntime([], [])
    result = CampaignRunner(tmp_path, runtime, _provider).run(max_lanes=4)

    assert result.stop_reason == "quota"
    assert [item[:2] for item in runtime.launched] == [(first.instance_id, "baseline")]
    assert not (tmp_path / "leases" / "0001-sympy__sympy-12419").exists()


def test_auth_marker_collection_fails_closed_for_unparseable_auth(tmp_path: Path) -> None:
    from benchmark.astra.lite_campaign import CampaignError, _auth_markers

    auth = tmp_path / "auth.json"
    auth.write_text("not-json", encoding="utf-8")

    with pytest.raises(CampaignError, match="authentication"):
        _auth_markers(auth)


def test_source_provenance_requires_the_clean_frozen_product_commit(tmp_path: Path) -> None:
    from benchmark.astra.lite_campaign import CampaignError, verify_frozen_source

    root = tmp_path / "source"
    root.mkdir()

    def clean_git(command, **_kwargs):
        if command[-2:] == ["status", "--porcelain"]:
            return subprocess.CompletedProcess(command, 0, "", "")
        if command[-1].endswith("^{commit}") and command[-1] != "HEAD^{commit}":
            return subprocess.CompletedProcess(
                command, 0, "71c8eae5ef1321c45c3d5c7aa8af1ffcded719b1\n", ""
            )
        if command[-1] == "HEAD^{commit}":
            return subprocess.CompletedProcess(
                command, 0, "71c8eae5ef1321c45c3d5c7aa8af1ffcded719b1\n", ""
            )
        return subprocess.CompletedProcess(
            command, 0, "51c22b9eec66b08bfa58ac8bad89bd964aaafd39\n", ""
        )

    provenance = verify_frozen_source(root, git_executor=clean_git)

    assert provenance.commit == "71c8eae5ef1321c45c3d5c7aa8af1ffcded719b1"
    assert provenance.tree == "51c22b9eec66b08bfa58ac8bad89bd964aaafd39"

    def dirty_git(command, **kwargs):
        if command[-2:] == ["status", "--porcelain"]:
            return subprocess.CompletedProcess(command, 0, " M benchmark/prompt_template.txt\n", "")
        return clean_git(command, **kwargs)

    with pytest.raises(CampaignError, match="clean"):
        verify_frozen_source(root, git_executor=dirty_git)
