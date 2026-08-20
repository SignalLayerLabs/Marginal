import pytest

from marginal.integrations.claude_code import installer


class FakeRunner:
    def __init__(self, results: dict[str, installer.CommandResult]) -> None:
        self.results = results
        self.calls: list[list[str]] = []

    def run(self, args: list[str]) -> installer.CommandResult:
        self.calls.append(args)
        for key, result in self.results.items():
            if key in args:
                return result
        return installer.CommandResult(0, "", "")


def _ok(stdout: str = "") -> installer.CommandResult:
    return installer.CommandResult(0, stdout, "")


def _fail(stderr: str) -> installer.CommandResult:
    return installer.CommandResult(1, "", stderr)


@pytest.fixture
def on_path(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(installer.shutil, "which", lambda name: f"/usr/bin/{name}")


def test_a_missing_cli_is_a_normal_answer(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(installer.shutil, "which", lambda name: None)
    report = installer.inspect_claude_code()
    assert report.available is False
    assert report.capability_level == "none"
    assert report.blocking_reasons == ("CLAUDE_CODE_NOT_FOUND",)
    assert installer.install().error_code == "CLAUDE_CODE_NOT_FOUND"
    assert installer.uninstall().error_code == "CLAUDE_CODE_NOT_FOUND"


def test_a_supported_version_reports_observe(on_path: None) -> None:
    runner = FakeRunner({"--version": _ok("2.1.233 (Claude Code)")})
    report = installer.inspect_claude_code(runner=runner)
    assert report.available is True
    assert report.version == "2.1.233"
    assert report.plugins_supported is True
    assert report.capability_level == "observe"
    assert report.blocking_reasons == ()
    assert report.to_dict()["capability_label"] == "Observe"


def test_an_old_version_blocks_installation(on_path: None) -> None:
    runner = FakeRunner({"--version": _ok("1.0.9 (Claude Code)")})
    report = installer.inspect_claude_code(runner=runner)
    assert report.plugins_supported is False
    assert "PLUGIN_SUPPORT_UNVERIFIED" in report.blocking_reasons


def test_an_unreadable_version_is_reported(on_path: None) -> None:
    runner = FakeRunner({"--version": _fail("boom")})
    report = installer.inspect_claude_code(runner=runner)
    assert "VERSION_UNAVAILABLE" in report.blocking_reasons


def test_install_adds_the_marketplace_then_the_plugin(on_path: None) -> None:
    runner = FakeRunner({})
    result = installer.install(runner=runner)
    assert result.installed is True
    assert result.changed is True
    assert result.selector == "marginal-claude-code@marginal"
    assert runner.calls[0][1:4] == ["plugin", "marketplace", "add"]
    assert runner.calls[1][1:3] == ["plugin", "install"]


def test_install_tolerates_an_existing_marketplace(on_path: None) -> None:
    runner = FakeRunner({"marketplace": _fail("marketplace already configured")})
    assert installer.install(runner=runner).installed is True


def test_install_reports_a_marketplace_failure(on_path: None) -> None:
    runner = FakeRunner({"marketplace": _fail("network unreachable")})
    result = installer.install(runner=runner)
    assert result.installed is False
    assert result.error_code == "MARKETPLACE_FAILED"
    assert result.message == "network unreachable"


def test_install_reports_a_plugin_failure(on_path: None) -> None:
    runner = FakeRunner({"install": _fail("unknown plugin")})
    result = installer.install(runner=runner)
    assert result.installed is False
    assert result.error_code == "INSTALL_FAILED"


def test_uninstall_is_reversible_and_idempotent(on_path: None) -> None:
    assert installer.uninstall(runner=FakeRunner({})).installed is False
    absent = installer.uninstall(runner=FakeRunner({"uninstall": _fail("plugin not installed")}))
    assert absent.installed is False
    assert absent.error_code == ""


def test_uninstall_reports_a_real_failure(on_path: None) -> None:
    result = installer.uninstall(runner=FakeRunner({"uninstall": _fail("permission denied")}))
    assert result.installed is True
    assert result.error_code == "UNINSTALL_FAILED"


def test_the_subprocess_runner_never_inherits_secrets(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "must-not-be-inherited")
    runner = installer.SubprocessRunner(timeout_seconds=10.0)
    result = runner.run(["/usr/bin/env"])
    assert "must-not-be-inherited" not in result.stdout


def test_the_subprocess_runner_reports_a_missing_binary() -> None:
    runner = installer.SubprocessRunner()
    result = runner.run(["/nonexistent/marginal-test-binary"])
    assert result.returncode == 127
