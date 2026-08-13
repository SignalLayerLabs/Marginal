#!/usr/bin/env python3
"""Build the deterministic ZIP uploaded to the OpenAI Plugins Directory."""

from __future__ import annotations

import argparse
import json
import stat
import zipfile
from pathlib import Path

REPRODUCIBLE_TIMESTAMP = (1980, 1, 1, 0, 0, 0)
EXCLUDED_PARTS = {"__pycache__", ".DS_Store"}


def _included_files(plugin_root: Path) -> list[Path]:
    files: list[Path] = []
    for path in plugin_root.rglob("*"):
        relative = path.relative_to(plugin_root)
        if any(part in EXCLUDED_PARTS for part in relative.parts):
            continue
        if path.is_symlink():
            raise ValueError(f"submission archive cannot contain symlinks: {relative}")
        if path.is_file() and path.suffix != ".pyc":
            files.append(path)
    return sorted(files, key=lambda path: path.relative_to(plugin_root).as_posix())


def build_submission_archive(repo: Path, *, output_dir: Path) -> Path:
    """Package one plugin root at the archive root using stable metadata."""

    repo = repo.resolve()
    plugin_root = repo / "plugins" / "marginal"
    manifest = json.loads(
        (plugin_root / ".codex-plugin" / "plugin.json").read_text(encoding="utf-8")
    )
    version = manifest["version"]
    output_dir.mkdir(parents=True, exist_ok=True)
    archive_path = output_dir / f"marginal-plugin-directory-{version}.zip"

    with zipfile.ZipFile(
        archive_path,
        "w",
        compression=zipfile.ZIP_DEFLATED,
        compresslevel=9,
    ) as archive:
        for path in _included_files(plugin_root):
            relative = path.relative_to(plugin_root).as_posix()
            info = zipfile.ZipInfo(relative, date_time=REPRODUCIBLE_TIMESTAMP)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.create_system = 3
            mode = 0o755 if path.stat().st_mode & stat.S_IXUSR else 0o644
            info.external_attr = (stat.S_IFREG | mode) << 16
            archive.writestr(info, path.read_bytes(), compresslevel=9)

    return archive_path


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Build the deterministic MARGINAL Plugins Directory ZIP."
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("dist"),
        help="Archive destination (default: dist)",
    )
    args = parser.parse_args()
    repo = Path(__file__).resolve().parents[1]
    print(build_submission_archive(repo, output_dir=args.output_dir))


if __name__ == "__main__":
    main()
