#!/usr/bin/env python3
"""Reproducibly build the dependency-free MARGINAL Codex runtime zipapp."""

from __future__ import annotations

import argparse
import hashlib
import json
import tempfile
import zipfile
from dataclasses import dataclass
from pathlib import Path

_ZIP_TIMESTAMP = (2020, 1, 1, 0, 0, 0)
_MAIN = (
    b"from marginal.integrations.codex.service import hook_main\n"
    b"raise SystemExit(hook_main())\n"
)


@dataclass(frozen=True, slots=True)
class PluginBuild:
    zipapp: Path
    source_hash: str
    sha256: str


def _source_files(repo: Path) -> list[Path]:
    package = repo / "src" / "marginal"
    return sorted(
        path
        for path in package.rglob("*")
        if (
            path.is_file()
            and "__pycache__" not in path.parts
            and path.suffix in {".py", ".json"}
        )
        or path == package / "py.typed"
    )


def _source_hash(repo: Path, files: list[Path]) -> str:
    digest = hashlib.sha256()
    for path in files:
        relative = path.relative_to(repo / "src").as_posix().encode("utf-8")
        digest.update(relative + b"\0" + path.read_bytes() + b"\0")
    digest.update(b"__main__.py\0" + _MAIN)
    return digest.hexdigest()


def _write_archive(target: Path, repo: Path, files: list[Path]) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(
        target,
        "w",
        compression=zipfile.ZIP_DEFLATED,
        compresslevel=9,
    ) as archive:
        entries = [("__main__.py", _MAIN)] + [
            (path.relative_to(repo / "src").as_posix(), path.read_bytes()) for path in files
        ]
        for name, content in sorted(entries):
            info = zipfile.ZipInfo(name, date_time=_ZIP_TIMESTAMP)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            info.create_system = 3
            archive.writestr(info, content, compress_type=zipfile.ZIP_DEFLATED, compresslevel=9)


def build_plugin_runtime(repo: str | Path, *, output_dir: str | Path) -> PluginBuild:
    root = Path(repo).resolve()
    destination = Path(output_dir).resolve()
    files = _source_files(root)
    source_hash = _source_hash(root, files)
    zipapp = destination / "marginal_runtime.pyz"
    _write_archive(zipapp, root, files)
    archive_hash = hashlib.sha256(zipapp.read_bytes()).hexdigest()
    return PluginBuild(zipapp=zipapp, source_hash=source_hash, sha256=archive_hash)


def _write_provenance(runtime_dir: Path, build: PluginBuild) -> None:
    payload = {
        "schema_version": 1,
        "builder": "scripts/build_codex_plugin.py",
        "python_requires": ">=3.10",
        "source_hash": build.source_hash,
        "sha256": build.sha256,
    }
    (runtime_dir / "provenance.json").write_text(
        json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    repo = Path(__file__).resolve().parents[1]
    committed_dir = repo / "plugins" / "marginal" / "runtime"
    if args.check:
        with tempfile.TemporaryDirectory(prefix="marginal-plugin-check-") as temporary:
            build = build_plugin_runtime(repo, output_dir=temporary)
            committed = committed_dir / "marginal_runtime.pyz"
            provenance = json.loads(
                (committed_dir / "provenance.json").read_text(encoding="utf-8")
            )
            if not committed.exists() or committed.read_bytes() != build.zipapp.read_bytes():
                raise SystemExit("committed Codex runtime is stale")
            if provenance.get("sha256") != build.sha256:
                raise SystemExit("Codex runtime provenance is stale")
            if provenance.get("source_hash") != build.source_hash:
                raise SystemExit("Codex runtime source hash is stale")
        return 0
    build = build_plugin_runtime(repo, output_dir=committed_dir)
    _write_provenance(committed_dir, build)
    print(f"built {build.zipapp} ({build.sha256})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
