from pathlib import Path

import pytest

from marginal.integrations.opencode import installer
from marginal.integrations.opencode.targets import (
    OPENCODE,
    PLUGIN_MARKER,
    TARGETS,
    resolve_target,
)


@pytest.fixture
def config_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
    return tmp_path / "config"


class FakeRunner:
    def __init__(self, result: installer.CommandResult) -> None:
        self.result = result

    def run(self, args: list[str]) -> installer.CommandResult:
        return self.result


def test_the_bundled_plugin_ships_with_its_marker() -> None:
    source = installer.bundled_plugin_path()
    assert source.is_file()
    assert PLUGIN_MARKER in source.read_text(encoding="utf-8")


def test_targets_resolve_by_name() -> None:
    assert resolve_target("opencode") is OPENCODE
    assert resolve_target(" OpenCode ") is OPENCODE
    with pytest.raises(ValueError):
        resolve_target("not-a-real-engine")
    assert set(TARGETS) >= {"opencode"}


def test_install_is_idempotent_and_reversible(config_home: Path) -> None:
    first = installer.install()
    assert first.installed is True
    assert first.changed is True
    plugin = Path(first.path)
    assert plugin.is_file()
    assert plugin.parent == config_home / "opencode" / "plugins"

    second = installer.install()
    assert second.installed is True
    assert second.changed is False

    removal = installer.uninstall()
    assert removal.installed is False
    assert removal.changed is True
    assert not plugin.exists()


def test_uninstalling_an_absent_plugin_is_a_success(config_home: Path) -> None:
    result = installer.uninstall()
    assert result.installed is False
    assert result.changed is False
    assert result.error_code == ""


def test_a_foreign_plugin_is_never_overwritten_or_removed(config_home: Path) -> None:
    plugin = OPENCODE.plugin_path()
    plugin.parent.mkdir(parents=True, exist_ok=True)
    plugin.write_text("export const Mine = async () => ({})\n", encoding="utf-8")

    blocked = installer.install()
    assert blocked.installed is False
    assert blocked.error_code == "FOREIGN_PLUGIN_PRESENT"

    refused = installer.uninstall()
    assert refused.error_code == "FOREIGN_PLUGIN_PRESENT"
    assert plugin.read_text(encoding="utf-8").startswith("export const Mine")


def test_a_missing_source_is_reported(config_home: Path, tmp_path: Path) -> None:
    result = installer.install(source=tmp_path / "absent.js")
    assert result.installed is False
    assert result.error_code == "PLUGIN_SOURCE_MISSING"


def test_the_data_root_is_configurable(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "share"))
    assert OPENCODE.data_root() == tmp_path / "share" / "marginal" / "opencode"
    monkeypatch.setenv("MARGINAL_OPENCODE_DATA", str(tmp_path / "elsewhere"))
    assert OPENCODE.data_root() == tmp_path / "elsewhere"


def test_a_missing_cli_is_a_normal_answer(
    config_home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(installer.shutil, "which", lambda name: None)
    report = installer.inspect_opencode()
    assert report.available is False
    assert report.capability_level == "none"
    assert report.blocking_reasons == ("OPENCODE_NOT_FOUND",)


def test_a_supported_version_reports_observe(
    config_home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(installer.shutil, "which", lambda name: f"/usr/bin/{name}")
    runner = FakeRunner(installer.CommandResult(0, "1.18.18\n", ""))
    report = installer.inspect_opencode(runner=runner)
    assert report.available is True
    assert report.version == "1.18.18"
    assert report.capability_level == "observe"
    assert report.plugin_installed is False
    assert report.to_dict()["capability_label"] == "Observe"


def test_an_old_version_blocks_installation(
    config_home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(installer.shutil, "which", lambda name: f"/usr/bin/{name}")
    runner = FakeRunner(installer.CommandResult(0, "1.2.3\n", ""))
    report = installer.inspect_opencode(runner=runner)
    assert report.plugins_supported is False
    assert "PLUGIN_SUPPORT_UNVERIFIED" in report.blocking_reasons


def test_an_installed_plugin_is_reported(
    config_home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    installer.install()
    monkeypatch.setattr(installer.shutil, "which", lambda name: f"/usr/bin/{name}")
    report = installer.inspect_opencode(
        runner=FakeRunner(installer.CommandResult(0, "1.18.18", ""))
    )
    assert report.plugin_installed is True


def test_the_subprocess_runner_never_inherits_secrets(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "must-not-be-inherited")
    result = installer.SubprocessRunner().run(["/usr/bin/env"])
    assert "must-not-be-inherited" not in result.stdout


def test_the_subprocess_runner_reports_a_missing_binary() -> None:
    assert installer.SubprocessRunner().run(["/nonexistent/marginal-test"]).returncode == 127
