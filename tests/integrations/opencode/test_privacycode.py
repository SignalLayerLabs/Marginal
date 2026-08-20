"""PrivacyCode is an OpenCode-compatible fork, governed by the same adapter.

These tests pin what must stay identical (the plugin, the bridge protocol, the
governance contract) and what must stay distinct (engine label, install location,
ledger location), so the two engines are never conflated in one ledger.
"""

from pathlib import Path

import pytest

from marginal.integrations.opencode import installer
from marginal.integrations.opencode.bridge import BridgeService
from marginal.integrations.opencode.targets import (
    OPENCODE,
    PRIVACYCODE,
    TARGETS,
    resolve_target,
)
from marginal.ledger import read_decision_ledger

from .conftest import SESSION_ID, RequestFactory


@pytest.fixture
def homes(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
    monkeypatch.delenv("MARGINAL_OPENCODE_DATA", raising=False)
    monkeypatch.delenv("MARGINAL_PRIVACYCODE_DATA", raising=False)
    return tmp_path


def test_privacycode_is_a_supported_target() -> None:
    assert resolve_target("privacycode") is PRIVACYCODE
    assert set(TARGETS) == {"opencode", "privacycode"}
    assert PRIVACYCODE.engine != OPENCODE.engine


def test_the_two_targets_never_share_a_location(homes: Path) -> None:
    assert PRIVACYCODE.plugin_path() != OPENCODE.plugin_path()
    assert PRIVACYCODE.data_root() != OPENCODE.data_root()
    assert PRIVACYCODE.plugin_path().parent == homes / "config" / "privacycode" / "plugins"
    assert PRIVACYCODE.data_root() == homes / "data" / "marginal" / "privacycode"


def test_the_data_root_override_is_target_specific(
    homes: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("MARGINAL_PRIVACYCODE_DATA", str(homes / "elsewhere"))
    assert PRIVACYCODE.data_root() == homes / "elsewhere"
    assert OPENCODE.data_root() == homes / "data" / "marginal" / "opencode"


def test_installing_binds_the_plugin_to_its_engine(homes: Path) -> None:
    result = installer.install(target=PRIVACYCODE)
    assert result.installed is True
    assert result.target == "privacycode"
    installed = Path(result.path).read_text(encoding="utf-8")
    assert 'process.env.MARGINAL_TARGET || "privacycode"' in installed
    assert '|| "opencode"' not in installed


def test_the_shipped_plugin_still_defaults_to_opencode() -> None:
    source = installer.bundled_plugin_path().read_text(encoding="utf-8")
    assert 'process.env.MARGINAL_TARGET || "opencode"' in source


def test_both_engines_can_be_installed_side_by_side(homes: Path) -> None:
    assert installer.install(target=OPENCODE).installed is True
    assert installer.install(target=PRIVACYCODE).installed is True
    assert OPENCODE.plugin_path().is_file()
    assert PRIVACYCODE.plugin_path().is_file()

    assert installer.uninstall(target=PRIVACYCODE).installed is False
    assert not PRIVACYCODE.plugin_path().exists()
    assert OPENCODE.plugin_path().is_file()


def test_rendering_rejects_a_source_without_a_target_declaration() -> None:
    with pytest.raises(ValueError):
        installer.render_plugin("// marginal-opencode-plugin\n", PRIVACYCODE)


def test_an_unrecognized_source_is_never_installed(homes: Path, tmp_path: Path) -> None:
    foreign = tmp_path / "foreign.js"
    foreign.write_text("export const Other = async () => ({})\n", encoding="utf-8")
    result = installer.install(target=PRIVACYCODE, source=foreign)
    assert result.installed is False
    assert result.error_code == "PLUGIN_SOURCE_UNRECOGNIZED"
    assert not PRIVACYCODE.plugin_path().exists()


def test_a_missing_cli_is_a_normal_answer(homes: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(installer.shutil, "which", lambda name: None)
    report = installer.inspect_opencode(target=PRIVACYCODE)
    assert report.target == "privacycode"
    assert report.blocking_reasons == ("PRIVACYCODE_NOT_FOUND",)


def test_the_ledger_records_the_forked_engine(homes: Path, requests: RequestFactory) -> None:
    service = BridgeService(target=PRIVACYCODE, data_root=homes / "ledger-root")
    assert service.handle("status", {}) == {
        "engine": "privacycode",
        "sessions": 0,
        "capability_level": "observe",
    }
    service.handle("session_start", requests.session())
    service.handle("tool_start", requests.tool_start())
    service.handle("tool_end", requests.tool_end(signals={"exit": 0}))
    service.handle("session_end", requests.session())
    records = read_decision_ledger(sorted(service.data_root.rglob("*.jsonl"))[0])
    assert {record["engine"] for record in records} == {"privacycode"}
    assert [record["event"] for record in records][-1] == "hook_session_end"


def test_the_bridge_entry_point_accepts_the_forked_target(homes: Path) -> None:
    from marginal.integrations.opencode.bridge import BridgeService as Service

    service = Service(target=resolve_target("privacycode"), data_root=homes / "data")
    assert service.target.engine == "privacycode"
    assert service.session_ids == ()
    assert SESSION_ID not in str(service.data_root)
