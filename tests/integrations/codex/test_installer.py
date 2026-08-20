from __future__ import annotations

from dataclasses import dataclass, field

from marginal.commons.config import CommonsMode, configure_commons_mode, load_commons_config
from marginal.integrations.codex.installer import (
    CommandResult,
    autopilot_consent_configured,
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


def test_install_can_persist_explicit_user_autopilot_consent(tmp_path) -> None:
    result = install(runner=RecordingRunner(), data_dir=tmp_path, autopilot_consent=True)

    assert result.installed is True
    assert result.autopilot_consent is True
    assert autopilot_consent_configured(tmp_path) is True


def test_install_persists_explicit_commons_choice_without_altering_autopilot(tmp_path) -> None:
    result = install(
        runner=RecordingRunner(),
        data_dir=tmp_path,
        autopilot_consent=True,
        commons_mode=CommonsMode.READ_ONLY,
    )

    assert result.installed is True
    assert result.commons_mode == "read_only"
    assert load_commons_config(tmp_path).mode is CommonsMode.READ_ONLY
    assert autopilot_consent_configured(tmp_path) is True


def test_install_defaults_to_local_only_without_persisting_or_enabling_network(tmp_path) -> None:
    result = install(runner=RecordingRunner(), data_dir=tmp_path)

    assert result.commons_mode == "local_only"
    assert load_commons_config(tmp_path).mode is CommonsMode.LOCAL_ONLY
    assert not (tmp_path / "user-config.json").exists()


def test_reinstall_without_a_mode_reports_and_preserves_persisted_contributor(tmp_path) -> None:
    configure_commons_mode(tmp_path, mode=CommonsMode.CONTRIBUTOR)
    before = (tmp_path / "user-config.json").read_bytes()

    result = install(runner=RecordingRunner(), data_dir=tmp_path)

    assert result.commons_mode == "contributor"
    assert (tmp_path / "user-config.json").read_bytes() == before
