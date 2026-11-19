"""Check archived adapted code and the original paper source snapshots."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from paper_sources import verify_sources

ROOT = Path(__file__).resolve().parents[2]


def main() -> None:
    lock = json.loads((Path(__file__).with_name("BASELINE_LOCK.json")).read_text(encoding="utf-8"))
    for relative, expected in lock["files"].items():
        path = ROOT / relative
        with path.open("rb") as source:
            actual = hashlib.file_digest(source, "sha256").hexdigest()
        if actual != expected:
            raise ValueError(f"Archived adapted code changed: {relative}")
    archive_root = Path(__file__).with_name("adapted")
    archive_hashes = json.loads((Path(__file__).with_name("ARCHIVED_FILES_SHA256.json")).read_text(encoding="utf-8"))
    actual_files = {path.relative_to(archive_root).as_posix() for path in archive_root.rglob("*")
                    if path.is_file() and "__pycache__" not in path.parts}
    if actual_files != set(archive_hashes):
        raise ValueError("Archived file list changed")
    for relative, expected in archive_hashes.items():
        with (archive_root / relative).open("rb") as source:
            if hashlib.file_digest(source, "sha256").hexdigest() != expected:
                raise ValueError(f"Archived file changed: {relative}")
    sources = verify_sources()
    print(json.dumps({"archived_code_files": len(archive_hashes), "official_sources": sources}, indent=2))


if __name__ == "__main__":
    main()
