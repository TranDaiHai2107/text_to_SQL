"""Run/resume paired ablations; gold test labels are NEVER read by this runner."""
import argparse
import hashlib
import json
from pathlib import Path
import platform
import re
import sqlite3
import sys
import time
from settings import ROOT, WORKSPACE, BASELINE, MODEL, EMBEDDING_MODEL
from retrieval import ThreeRAG, load
from model_client import ModelClient, RunBlocked
from pipeline import MODES, DEFAULT_MODES, PRIMARY_VARIANT, run_question


def dump(path, value):
    temporary = path.with_suffix(path.suffix+".tmp")
    temporary.write_text(json.dumps(value, indent=2)+"\n", encoding="utf-8")
    temporary.replace(path)


def definition(split, modes, model, effort, limit, sql_tokens=900, rewrite_tokens=256, primary_variant=None):
    files = ["settings.py", "retrieval.py", "sql_runtime.py", "model_client.py", "pipeline.py", "run.py"]
    return {"split":split, "modes":modes, "model":model, "reasoning_effort":effort,
            "embedding_model":EMBEDDING_MODEL, "temperature":0, "seed":42,
            "max_sql_completion_tokens":sql_tokens, "max_rewrite_completion_tokens":rewrite_tokens,
            "repair_retries":2, "question_limit":limit, "scorer":"official",
            "primary_variant":primary_variant or (PRIMARY_VARIANT if PRIMARY_VARIANT in modes else modes[-1]),
            "protocol_version":2,
            "gold_test_access_during_inference":False, "examples_split":"train_only",
            "code_sha256":{name:hashlib.sha256((ROOT/name).read_bytes()).hexdigest() for name in files},
            "application_source_sha256":{name:hashlib.sha256((WORKSPACE/name).read_bytes()).hexdigest()
                                         for name in ["rag_engine.py", "build_vector_db.py", "embedding_config.py", "sql_validator.py"]},
            "baseline_manifest_sha256":hashlib.sha256((BASELINE/"source_manifest.json").read_bytes()).hexdigest(),
            "python":platform.python_version(), "sqlite":sqlite3.sqlite_version}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-name", required=True)
    parser.add_argument("--split", choices=["dev", "test"], default="test")
    parser.add_argument("--modes", nargs="+", choices=MODES, default=DEFAULT_MODES)
    parser.add_argument("--primary-variant", choices=MODES, help="Freeze the dev-selected primary before a test run")
    parser.add_argument("--model", default=MODEL)
    parser.add_argument("--reasoning-effort", choices=["none", "low", "medium", "high"], default="none")
    parser.add_argument("--sql-tokens", type=int, default=900)
    parser.add_argument("--rewrite-tokens", type=int, default=256)
    parser.add_argument("--limit", type=int, default=0)
    args = parser.parse_args()
    if len(args.modes) != len(set(args.modes)):
        parser.error("Duplicate modes are not allowed")
    if args.primary_variant and args.primary_variant not in args.modes:
        parser.error("Primary variant must be included in --modes")
    if args.split == "test" and not args.primary_variant:
        parser.error("Choose --primary-variant on dev and specify it explicitly before test")
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,79}", args.run_name) or args.limit < 0 or not (64 <= args.sql_tokens <= 16384) or not (64 <= args.rewrite_tokens <= 4096):
        parser.error("Invalid run name/limit")
    run_dir = ROOT/"runs"/args.run_name
    run_dir.mkdir(parents=True, exist_ok=True)
    config = definition(args.split, args.modes, args.model, args.reasoning_effort, args.limit, args.sql_tokens, args.rewrite_tokens, args.primary_variant)
    if (run_dir/"config.json").is_file():
        if load(run_dir/"config.json") != config:
            raise ValueError("Configuration/code changed. Use a new run name; do not mix experiment versions.")
    else:
        dump(run_dir/"config.json", config)
    questions = load(BASELINE/"data/inputs"/(args.split+".json"))["data"]
    # Deterministic hash order, independent of difficulty, gold SQL or label.
    questions = sorted(questions, key=lambda r:hashlib.sha256(("apply_work_v1:"+r["id"]).encode()).hexdigest())
    if args.limit:
        questions = questions[:args.limit]
    done = {}
    records_path = run_dir/"records.jsonl"
    if records_path.is_file():
        for line in records_path.read_text(encoding="utf-8").splitlines():
            row = json.loads(line)
            if row["id"] in done:
                raise ValueError("Duplicate completed question IDs")
            done[row["id"]] = row
    if not set(done) <= {r["id"] for r in questions}:
        raise ValueError("Unexpected completed question ID")
    rag = ThreeRAG()
    rag.build()
    client = ModelClient(run_dir, args.model, args.reasoning_effort, args.sql_tokens, args.rewrite_tokens)
    def status(state, **extra):
        dump(run_dir/"status.json", {"state":state, "split":args.split,
            "complete_questions":len(done), "requested_questions":len(questions),
            "full_split_questions":1167 if args.split=="test" else 1163,
            "full_benchmark_complete":len(done)==len(questions) and not args.limit,
            "updated_at_unix":time.time(), **extra})
    status("running")
    try:
        for item in questions:
            if item["id"] in done:
                continue
            checkpoint_path = run_dir/"checkpoints"/(item["id"]+".json")
            checkpoint_path.parent.mkdir(exist_ok=True)
            checkpoint = {"id":item["id"], "question":item["question"], "variants":{}}
            def save_stage(mode, record):
                checkpoint["variants"][mode] = record
                dump(checkpoint_path, checkpoint)
            row = run_question(item, args.modes, rag, client, save_stage)
            with records_path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(row)+"\n")
                handle.flush()
            done[item["id"]] = row
            status("running")
            print(f"Completed paired question {len(done)}/{len(questions)}: "+item["id"]+
                  " | "+", ".join(k+"="+("null" if v["sql"]=="null" else "SQL" if v["execution"]["valid"] else "ERROR")
                                    for k,v in row["variants"].items()), flush=True)
    except RunBlocked as error:
        status("blocked_by_api_quota_or_service", reason=str(error))
        print(str(error), flush=True)
        return 2
    status("complete")
    return 0


if __name__ == "__main__":
    sys.exit(main())

