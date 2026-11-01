"""Private IO and read-only SQL utilities; no API clients or legacy mutations."""
from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
WORKSPACE = HERE.parents[1]
BASELINE = WORKSPACE / "baselines/probgate_ehrsql_2024"
DATABASE = BASELINE / "upstream/src/data/mimic_iv/mimic_iv.sqlite"
SPLITS = {"train": "train", "validation": "dev", "test": "test"}


def load(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def dump(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")


def sha(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def jsonl(path):
    return [json.loads(line) for line in Path(path).read_text(encoding="utf-8").splitlines() if line.strip()]


def write_jsonl(path, rows):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(row, ensure_ascii=False, allow_nan=False) + "\n" for row in rows), encoding="utf-8")


def legacy():
    spec = importlib.util.spec_from_file_location("_english_extension_baseline_core", BASELINE / "baseline_core.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def verify_frozen():
    lock = load(WORKSPACE / "experiments/research_validation/V5_LOCK.json")
    for name, digest in lock["files"].items():
        if sha(WORKSPACE / name) != digest:
            raise ValueError("Frozen artifact changed: " + name)
    return len(lock["files"])
