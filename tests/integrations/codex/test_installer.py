from __future__ import annotations

from dataclasses import dataclass, field

from marginal.integrations.codex.installer import (
    CommandResult,
    inspect_codex,
    install,
    uninstall,
)


@dataclass
class RecordingRunner:
    version: str = "codex-cli 0.147.0\n"
    hooks: bool = True
    plugins: bool = True
    calls: list[list[str]] = field(default_factory=list)

    def run(self, args: list[str]) -> CommandResult:
        self.calls.append(args)
        if args == ["codex", "--version"]:
            return CommandResult(0, self.version, "")
        if args == ["codex", "features", "list"]:
            return CommandResult(
                0,
                f"hooks stable {str(self.hooks).lower()}\n"
                f"plugins stable {str(self.plugins).lower()}\n",
                "",
            )
        if args == ["codex", "plugin", "marketplace", "list", "--json"]:
            return CommandResult(0, "[]", "")
        if args == ["codex", "plugin", "list", "--available", "--json"]:
            return CommandResult(0, "[]", "")
        return CommandResult(0, "{}", "")


def test_discovery_never_reads_auth() -> None:
    runner = RecordingRunner()

    report = inspect_codex(runner=runner)

    assert report.capability_level == "tool_enforcement"
    assert report.version == "0.147.0"
    assert all("auth.json" not in " ".join(call) for call in runner.calls)


def test_missing_hooks_refuses_enforcement_claim() -> None:
    report = inspect_codex(runner=RecordingRunner(hooks=False))

    assert report.capability_level == "observe"
    assert "HOOKS_UNAVAILABLE" in report.blocking_reasons


def test_install_uses_native_codex_plugin_commands() -> None:
    runner = RecordingRunner()

    result = install(
        runner=runner,
        repository="SignalLayerLabs/Marginal",
        ref="main",
    )

    assert result.installed
    assert [
        "codex",
        "plugin",
        "marketplace",
        "add",
        "SignalLayerLabs/Marginal",
        "--ref",
        "main",
        "--json",
    ] in runner.calls
    assert ["codex", "plugin", "add", "marginal@marginal", "--json"] in runner.calls


def test_install_refuses_when_stable_capabilities_are_missing() -> None:
    runner = RecordingRunner(plugins=False)

    result = install(runner=runner)

    assert not result.installed
    assert result.error_code == "CODEX_CAPABILITIES_UNAVAILABLE"
    assert not any(call[1:3] == ["plugin", "add"] for call in runner.calls)


def test_uninstall_uses_native_command() -> None:
    runner = RecordingRunner()

    result = uninstall(runner=runner)

    assert result.installed is False
    assert ["codex", "plugin", "remove", "marginal@marginal", "--json"] in runner.calls
