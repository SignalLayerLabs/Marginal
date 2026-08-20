from __future__ import annotations

import json
import os
import stat
from pathlib import Path

import pytest

import marginal.commons.config as commons_config
from marginal.commons.config import (
    CommonsMode,
    configure_commons_mode,
    load_commons_config,
)
from marginal.integrations.codex.installer import (
    autopilot_consent_configured,
    configure_autopilot_consent,
)


def test_missing_config_defaults_to_local_only_without_creating_a_file(tmp_path: Path) -> None:
    assert load_commons_config(tmp_path).mode is CommonsMode.LOCAL_ONLY
    assert not (tmp_path / "user-config.json").exists()


@pytest.mark.parametrize("mode", list(CommonsMode))
def test_explicit_mode_choice_persists_in_owner_only_user_config(
    tmp_path: Path, mode: CommonsMode
) -> None:
    configured = configure_commons_mode(tmp_path, mode=mode)

    path = tmp_path / "user-config.json"
    assert configured.mode is mode
    assert load_commons_config(tmp_path).mode is mode
    assert json.loads(path.read_text(encoding="utf-8")) == {
        "commons_mode": mode.value,
        "schema_version": 1,
    }
    if os.name == "posix":
        assert stat.S_IMODE(path.stat().st_mode) == 0o600
        assert stat.S_IMODE(tmp_path.stat().st_mode) == 0o700


def test_commons_and_autopilot_updates_preserve_each_others_explicit_choice(tmp_path: Path) -> None:
    configure_autopilot_consent(tmp_path, granted=True)
    configure_commons_mode(tmp_path, mode=CommonsMode.CONTRIBUTOR)
    assert autopilot_consent_configured(tmp_path) is True

    configure_autopilot_consent(tmp_path, granted=False)
    payload = json.loads((tmp_path / "user-config.json").read_text(encoding="utf-8"))
    assert payload == {
        "autopilot_consent": False,
        "commons_mode": "contributor",
        "schema_version": 1,
    }
    assert load_commons_config(tmp_path).mode is CommonsMode.CONTRIBUTOR


def test_config_rejects_symlink_targets_and_unsafe_existing_permissions(tmp_path: Path) -> None:
    target = tmp_path / "outside.json"
    target.write_text('{"schema_version":1,"commons_mode":"read_only"}\n', encoding="utf-8")
    target.chmod(0o600)
    link_root = tmp_path / "linked"
    link_root.mkdir()
    try:
        (link_root / "user-config.json").symlink_to(target)
    except (OSError, NotImplementedError):
        pytest.skip("symbolic links are not available")

    with pytest.raises(ValueError, match="symbolic link"):
        load_commons_config(link_root)
    with pytest.raises(ValueError, match="symbolic link"):
        configure_commons_mode(link_root, mode=CommonsMode.CONTRIBUTOR)
    assert "contributor" not in target.read_text(encoding="utf-8")

    unsafe = tmp_path / "unsafe"
    unsafe.mkdir()
    path = unsafe / "user-config.json"
    path.write_text('{"schema_version":1,"commons_mode":"read_only"}\n', encoding="utf-8")
    if os.name == "posix":
        path.chmod(0o644)
        with pytest.raises(ValueError, match="owner-only"):
            load_commons_config(unsafe)


def test_failed_atomic_replace_preserves_existing_choices(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    configure_autopilot_consent(tmp_path, granted=True)
    path = tmp_path / "user-config.json"
    before = path.read_bytes()

    def fail_replace(source: object, destination: object, **directory_descriptors: object) -> None:
        del source, destination, directory_descriptors
        raise OSError("synthetic replace failure")

    monkeypatch.setattr(os, "replace", fail_replace)
    with pytest.raises(OSError, match="synthetic"):
        configure_commons_mode(tmp_path, mode=CommonsMode.READ_ONLY)

    assert path.read_bytes() == before
    assert not list(tmp_path.glob(".user-config-*.tmp"))


def test_atomic_update_holds_the_open_parent_across_a_path_swap(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    data_root = tmp_path / "data"
    configure_commons_mode(data_root, mode=CommonsMode.CONTRIBUTOR)
    displaced = tmp_path / "displaced-data"
    outside = tmp_path / "outside"
    outside.mkdir()
    outside_config = outside / "user-config.json"
    outside_config.write_text(
        '{"commons_mode":"local_only","schema_version":1}\n', encoding="utf-8"
    )
    outside_config.chmod(0o600)
    original_open = os.open
    swapped = False

    def swapping_open(
        name: object,
        flags: int,
        mode: int = 0o777,
        *,
        dir_fd: int | None = None,
    ) -> int:
        nonlocal swapped
        if dir_fd is None:
            descriptor = original_open(name, flags, mode)
        else:
            descriptor = original_open(name, flags, mode, dir_fd=dir_fd)
        if not swapped and name == data_root.name and dir_fd is not None and flags & os.O_DIRECTORY:
            data_root.rename(displaced)
            data_root.symlink_to(outside, target_is_directory=True)
            swapped = True
        return descriptor

    monkeypatch.setattr(commons_config.os, "open", swapping_open)

    configure_commons_mode(data_root, mode=CommonsMode.READ_ONLY)

    assert swapped is True
    assert (
        json.loads((displaced / "user-config.json").read_text(encoding="utf-8"))["commons_mode"]
        == "read_only"
    )
    assert json.loads(outside_config.read_text(encoding="utf-8"))["commons_mode"] == "local_only"


def test_atomic_update_retries_short_writes_until_the_config_is_complete(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    original_write = os.write
    writes = 0

    def short_write(descriptor: int, data: bytes) -> int:
        nonlocal writes
        writes += 1
        return original_write(descriptor, data[:3])

    monkeypatch.setattr(commons_config.os, "write", short_write)

    configure_commons_mode(tmp_path, mode=CommonsMode.CONTRIBUTOR)

    assert writes > 1
    assert load_commons_config(tmp_path).mode is CommonsMode.CONTRIBUTOR


def test_atomic_update_preserves_the_old_file_when_a_partial_write_errors(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    configure_commons_mode(tmp_path, mode=CommonsMode.CONTRIBUTOR)
    path = tmp_path / "user-config.json"
    before = path.read_bytes()
    original_write = os.write
    writes = 0

    def interrupted_write(descriptor: int, data: bytes) -> int:
        nonlocal writes
        writes += 1
        if writes == 1:
            return original_write(descriptor, data[:4])
        raise OSError("synthetic interrupted write")

    monkeypatch.setattr(commons_config.os, "write", interrupted_write)

    with pytest.raises(OSError, match="interrupted write"):
        configure_commons_mode(tmp_path, mode=CommonsMode.READ_ONLY)

    assert path.read_bytes() == before
    assert not list(tmp_path.glob(".user-config-*.tmp"))


def test_config_rejects_boolean_schema_versions_instead_of_treating_them_as_one(
    tmp_path: Path,
) -> None:
    path = tmp_path / "user-config.json"
    path.write_text('{"commons_mode":"contributor","schema_version":true}\n', encoding="utf-8")
    path.chmod(0o600)

    with pytest.raises(ValueError, match="schema version 1"):
        load_commons_config(tmp_path)


@pytest.mark.parametrize("value", ["LOCAL_ONLY", " contributor", "read-only", "custom"])
def test_mode_parser_does_not_normalize_or_create_namespaces(value: str) -> None:
    with pytest.raises(ValueError, match="Commons mode"):
        CommonsMode.parse(value)
