"""Select a Python interpreter compatible with the bundled MARGINAL runtime."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys

_MINIMUM_VERSION = (3, 10)
_VERSIONED_NAMES = ("python3.13", "python3.12", "python3.11", "python3.10")


def _probe(command: tuple[str, ...]) -> bool:
    environment = {
        name: value
        for name in ("PATH", "SYSTEMROOT")
        if (value := os.environ.get(name)) is not None
    }
    environment["PYTHONNOUSERSITE"] = "1"
    try:
        completed = subprocess.run(
            [
                *command,
                "-I",
                "-c",
                "import sys; raise SystemExit(sys.version_info < (3, 10))",
            ],
            check=False,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            env=environment,
            timeout=2,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    return completed.returncode == 0


def compatible_python() -> tuple[str, ...]:
    """Return an executable command for Python 3.10+ without importing user packages."""

    if sys.version_info[:2] >= _MINIMUM_VERSION:
        return (sys.executable,)

    for name in _VERSIONED_NAMES:
        executable = shutil.which(name)
        if executable:
            return (executable,)

    if os.name == "nt":
        launcher = shutil.which("py")
        if launcher:
            for version in ("-3.13", "-3.12", "-3.11", "-3.10"):
                command = (launcher, version)
                if _probe(command):
                    return command

    python3 = shutil.which("python3")
    if python3 and _probe((python3,)):
        return (python3,)
    raise RuntimeError("MARGINAL requires Python 3.10 or newer")
