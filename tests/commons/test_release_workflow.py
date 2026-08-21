from __future__ import annotations

import re
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = ROOT / ".github" / "workflows" / "commons-release.yml"


def _workflow() -> dict[str, object]:
    return yaml.load(WORKFLOW.read_text(encoding="utf-8"), Loader=yaml.BaseLoader)


def test_release_workflow_has_only_dispatch_and_ten_minute_schedule() -> None:
    workflow = _workflow()
    triggers = workflow["on"]
    assert set(triggers) == {"workflow_dispatch", "schedule"}
    assert triggers["schedule"] == [{"cron": "*/10 * * * *"}]
    assert workflow["permissions"] == {"contents": "read"}


def test_release_workflow_uses_trusted_main_environment_and_data_checkout() -> None:
    workflow = _workflow()
    release = workflow["jobs"]["release"]
    assert release["environment"] == "commons-production"
    assert "github.repository == 'SignalLayerLabs/Marginal'" in release["if"]
    assert "github.ref == 'refs/heads/main'" in release["if"]
    steps = release["steps"]
    checkout = next(step for step in steps if step.get("name") == "Checkout trusted MARGINAL")
    assert checkout["with"] == {"path": "marginal", "persist-credentials": "false"}
    commons = next(step for step in steps if step.get("name") == "Checkout Commons as data")
    assert commons["with"] == {
        "repository": "SignalLayerLabs/Marginal-Commons",
        "ref": "main",
        "fetch-depth": "0",
        "path": "commons-data",
        "persist-credentials": "false",
    }


def test_release_workflow_verifies_current_state_and_pins_pages_deploy() -> None:
    workflow = _workflow()
    steps = workflow["jobs"]["release"]["steps"]
    combined = "\n".join(str(step.get("run", "")) for step in steps)
    assert "commons-pack-v1.json" in combined
    assert "commons-pack-v1.sig.json" in combined
    assert "--verify-pack" in combined
    assert "--current-pack" in combined
    assert "npx wrangler@4.124.0 pages deploy" in combined
    assert "--project-name marginal-commons" in combined
    assert "--branch main" not in combined
    deploy = next(step for step in steps if step.get("name") == "Deploy signed release")
    assert deploy["env"] == {
        "CLOUDFLARE_API_TOKEN": "${{ secrets.CLOUDFLARE_API_TOKEN }}",
        "CLOUDFLARE_ACCOUNT_ID": "${{ secrets.CLOUDFLARE_ACCOUNT_ID }}",
    }


def test_release_workflow_exposes_only_required_release_secrets() -> None:
    workflow = _workflow()
    steps = workflow["jobs"]["release"]["steps"]
    build = next(step for step in steps if step.get("name") == "Build signed candidate")
    assert build["env"] == {
        "COMMONS_RELEASE_PRIVATE_KEY_B64URL": ("${{ secrets.COMMONS_RELEASE_PRIVATE_KEY_B64URL }}")
    }


def test_release_workflow_pins_every_action_and_hash_locks_signing_dependencies() -> None:
    workflow = _workflow()
    steps = workflow["jobs"]["release"]["steps"]
    action_reference = re.compile(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+@[0-9a-f]{40}\Z")
    used_actions = [step["uses"] for step in steps if "uses" in step]
    assert used_actions
    assert all(action_reference.fullmatch(reference) for reference in used_actions)

    install = next(
        step for step in steps if step.get("name") == "Install trusted release dependencies"
    )
    command = install["run"]
    assert "--require-hashes" in command
    assert "--only-binary=:all:" in command
    assert "requirements/commons-release.txt" in command

    requirements = (ROOT / "requirements" / "commons-release.txt").read_text(encoding="utf-8")
    assert "cryptography==" in requirements
    assert "cffi==" in requirements
    assert "pycparser==" in requirements
    assert ">=" not in requirements
    assert requirements.count("--hash=sha256:") >= 4


def test_unsigned_bootstrap_checks_all_production_deployment_pages() -> None:
    workflow = _workflow()
    steps = workflow["jobs"]["release"]["steps"]
    compare = next(
        step for step in steps if step.get("name") == "Compare current signed production state"
    )
    command = compare["run"]
    assert "page=${deployment_page}" in command
    assert "per_page=25" in command
    assert "per_page=100" not in command
    assert "total_pages" in command
    assert "deployment_page=$((deployment_page + 1))" in command
