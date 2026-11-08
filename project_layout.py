"""Current benchmark and archived provenance locations after 2026-11-06 cleanup."""
from pathlib import Path

WORKSPACE = Path(__file__).resolve().parent
HISTORY = WORKSPACE / "_archive/20261106/workspace"
HISTORICAL_EXPERIMENTS = HISTORY / "experiments"


def historical_file(relative):
    """Find original locked bytes after relocation; shared baseline stays active."""
    relative = Path(relative)
    archived = HISTORY / relative
    return archived if archived.is_file() else WORKSPACE / relative


def verify_historical():
    import hashlib
    import json
    import zipfile
    lock = json.loads((HISTORICAL_EXPERIMENTS / "research_validation/V5_LOCK.json").read_text(encoding="utf-8"))
    for name, expected in lock["files"].items():
        file = historical_file(name)
        if not file.is_file():
            with zipfile.ZipFile(WORKSPACE / "_archive/locked_source_evidence.zip") as evidence:
                actual = hashlib.sha256(evidence.read(name)).hexdigest()
            if actual != expected:
                raise ValueError("Historical evidence changed: " + name)
            continue
        digest = hashlib.sha256()
        with file.open("rb") as stream:
            for block in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(block)
        if digest.hexdigest() != expected:
            raise ValueError("Historical artifact changed: " + name)
    return len(lock["files"])
