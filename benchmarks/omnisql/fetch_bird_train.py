"""Fetch BIRD *train* questions (question, evidence, SQL) for Ours' few-shot retrieval layer.

Only ``data/bird/train/train.json`` is read from the authors' OmniSQL-datasets ZIP (pinned
revision), via HTTP ranges. Train databases are not needed: demonstrations are text only.
BIRD dev gold SQL is never used as a demonstration.
"""
from __future__ import annotations

import hashlib
import json
import zipfile

from fetch_official_prompt import ROOT, URL, RangeFile

MEMBER = "data/bird/train/train.json"
TARGET = ROOT / "data" / "benchmarks" / "bird" / "bird_train.json"


def main() -> None:
    with RangeFile() as remote, zipfile.ZipFile(remote) as archive:
        data = archive.read(MEMBER)
    rows = json.loads(data)
    if len(rows) != 9428 or not all({"db_id", "question", "evidence", "SQL"} <= set(r) for r in rows):
        raise ValueError(f"Unexpected BIRD train file ({len(rows)} rows)")
    TARGET.parent.mkdir(parents=True, exist_ok=True)
    TARGET.write_bytes(data)
    manifest = {"source_url": URL, "member": MEMBER, "bytes": len(data),
                "sha256": hashlib.sha256(data).hexdigest(), "questions": len(rows),
                "databases": len({r["db_id"] for r in rows})}
    (TARGET.parent / "bird_train_manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(manifest, indent=2))


if __name__ == "__main__":
    main()
