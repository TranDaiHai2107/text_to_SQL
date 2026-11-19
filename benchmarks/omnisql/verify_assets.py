"""Verify the pinned OmniSQL source and BIRD dev inputs before scoring."""
from __future__ import annotations

import hashlib
import json
from contextlib import closing
from pathlib import Path
import sqlite3

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
DATA = ROOT / "data" / "benchmarks" / "bird"


def sha256(path: Path) -> str:
    with path.open("rb") as source:
        return hashlib.file_digest(source, "sha256").hexdigest()


def verify(*, include_archive: bool = False) -> dict:
    lock = json.loads((HERE / "SOURCE_LOCK.json").read_text(encoding="utf-8"))
    source = ROOT / lock["official_source_path"]
    full_manifest = json.loads((HERE / "source_files_sha256.json").read_text(encoding="utf-8"))
    if len(full_manifest) < 60:
        raise ValueError("Official source manifest is incomplete")
    actual_files = {path.relative_to(source).as_posix() for path in source.rglob("*")
                    if path.is_file() and "__pycache__" not in path.parts}
    if actual_files != set(full_manifest):
        raise ValueError("Official source file list changed")
    for relative, expected in full_manifest.items():
        if sha256(source / relative) != expected:
            raise ValueError(f"Official source changed: {relative}")
    for relative, expected in lock["key_file_sha256"].items():
        path = source / relative
        if sha256(path) != expected:
            raise ValueError(f"Official source changed: {path}")
    checks = {
        DATA / "dev_20240627" / "dev.json": lock["bird_dev_json_sha256"],
        DATA / "dev_20240627" / "dev_tables.json": lock["bird_tables_sha256"],
        DATA / "omnisql_dev_bird.json": lock["omnisql_processed_prompt_sha256"],
    }
    if include_archive:
        checks[DATA / "dev.zip"] = lock["bird_archive_sha256"]
    for path, expected in checks.items():
        if sha256(path) != expected:
            raise ValueError(f"Benchmark asset changed: {path}")
    gold = json.loads((DATA / "dev_20240627" / "dev.json").read_text(encoding="utf-8"))
    prompts = json.loads((DATA / "omnisql_dev_bird.json").read_text(encoding="utf-8"))
    if len(gold) != len(prompts) or len(gold) != lock["bird_dev_questions"]:
        raise ValueError("Question count differs from paper")
    for index, (item, prompt) in enumerate(zip(gold, prompts)):
        if item["question"] not in prompt["input_seq"] or item["SQL"] not in prompt["output_seq"]:
            raise ValueError(f"Prompt/gold alignment differs at row {index}")
    db_root = DATA / "dev_20240627" / "dev_databases"
    db_ids = {item["db_id"] for item in gold}
    db_hashes = json.loads((HERE / "bird_db_sha256.json").read_text(encoding="utf-8"))
    if len(db_ids) != lock["bird_dev_databases"]:
        raise ValueError("Database count differs from paper")
    if len(db_hashes) != len(db_ids):
        raise ValueError("Database checksum manifest is incomplete")
    for db_id in db_ids:
        db_file = db_root / db_id / f"{db_id}.sqlite"
        if not db_file.is_file():
            raise FileNotFoundError(db_file)
        relative = f"{db_id}/{db_id}.sqlite"
        if sha256(db_file) != db_hashes[relative]:
            raise ValueError(f"Database changed: {db_file}")
        with closing(sqlite3.connect(f"file:{db_file.as_posix()}?mode=ro", uri=True)) as connection:
            if not connection.execute("SELECT name FROM sqlite_master WHERE type='table' LIMIT 1").fetchone():
                raise ValueError(f"Empty database: {db_file}")
    return {"source_commit": lock["source_commit"], "questions": len(gold),
            "databases": len(db_ids), "prompt_sha256": lock["omnisql_processed_prompt_sha256"]}


if __name__ == "__main__":
    print(json.dumps(verify(include_archive=True), indent=2))
