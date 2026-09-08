from __future__ import annotations

import os
import subprocess
from pathlib import Path


def test_pro_launcher_executes_packaged_native_codex_with_vendor_environment(
    tmp_path: Path,
) -> None:
    package_root = tmp_path / "codex"
    target_root = (
        package_root
        / "node_modules"
        / "@openai"
        / "codex-linux-x64"
        / "vendor"
        / "x86_64-unknown-linux-musl"
    )
    native_codex = target_root / "bin" / "codex"
    vendor_rg = target_root / "codex-path" / "rg"
    native_codex.parent.mkdir(parents=True)
    vendor_rg.parent.mkdir(parents=True)
    native_codex.write_text(
        "#!/bin/sh\n"
        "set -eu\n"
        "test \"$1\" = --version\n"
        "test \"$(command -v rg)\" = \"$CODEX_TEST_EXPECTED_RG\"\n"
        "test \"$CODEX_MANAGED_PACKAGE_ROOT\" = \"$CODEX_TEST_EXPECTED_ROOT\"\n"
        "test \"$CODEX_MANAGED_BY_NPM\" = 1\n"
        "test \"${CODEX_MANAGED_BY_BUN-unset}\" = unset\n"
        "printf 'codex 0.153.4\\n'\n",
        encoding="utf-8",
    )
    vendor_rg.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    native_codex.chmod(0o755)
    vendor_rg.chmod(0o755)
    launcher = Path("benchmark/container/pro-codex-native-wrapper.sh")
    environment = {
        **os.environ,
        "CODEX_PACKAGE_ROOT": str(package_root),
        "CODEX_TEST_EXPECTED_RG": str(vendor_rg),
        "CODEX_TEST_EXPECTED_ROOT": str(package_root),
        "CODEX_MANAGED_BY_BUN": "stale",
    }

    completed = subprocess.run(
        ["/bin/sh", str(launcher), "--version"],
        check=False,
        capture_output=True,
        text=True,
        env=environment,
    )

    assert completed.returncode == 0, completed.stderr
    assert completed.stdout == "codex 0.153.4\n"
