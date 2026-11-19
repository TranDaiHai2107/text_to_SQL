"""Byte-compare extracted BIRD dev files with both official ZIP layers."""
from __future__ import annotations

import json
from pathlib import Path
import zipfile

from verify_assets import DATA, verify


def compare_archive(archive_path: Path, target_root: Path) -> int:
    checked = 0
    with zipfile.ZipFile(archive_path) as archive:
        for entry in archive.infolist():
            if entry.is_dir() or entry.filename.startswith("__MACOSX/"):
                continue
            target = (target_root / entry.filename).resolve()
            if not target.is_relative_to(target_root.resolve()) or not target.is_file():
                raise ValueError(f"Missing or unsafe extracted member: {entry.filename}")
            with archive.open(entry) as upstream, target.open("rb") as local:
                while upstream_chunk := upstream.read(1024 * 1024):
                    if upstream_chunk != local.read(len(upstream_chunk)):
                        raise ValueError(f"Extracted file differs: {entry.filename}")
                if local.read(1):
                    raise ValueError(f"Extracted file has extra bytes: {entry.filename}")
            checked += 1
    return checked


if __name__ == "__main__":
    assets = verify(include_archive=True)
    outer = compare_archive(DATA / "dev.zip", DATA)
    nested_dir = DATA / "dev_20240627"
    nested = compare_archive(nested_dir / "dev_databases.zip", nested_dir)
    print(json.dumps({**assets, "outer_files_byte_equal": outer,
                      "nested_files_byte_equal": nested}, indent=2))
