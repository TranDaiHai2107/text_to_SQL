"""Offline audit of pinned public benchmarks; never calls an LLM."""
import hashlib
import json
from pathlib import Path
import sqlite3
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parent
SOURCES = ROOT / "sources"


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def main():
    manifest = {"checked_on": "2026-10-09", "repositories": {}, "ehrsql_2024": {}, "mimicsql": {}}
    for name in ("ehrsql-2024", "TREQS", "ast-icl", "SCARE", "ClinSQL"):
        repo = SOURCES / name
        tracked = subprocess.check_output(["git", "-C", str(repo), "ls-files"], text=True).splitlines()
        if name == "ClinSQL":
            tracked = [x for x in tracked if x.startswith("data/") or x == "README.md" or x.startswith("evaluation/")]
        manifest["repositories"][name] = {
            "commit": subprocess.check_output(["git", "-C", str(repo), "rev-parse", "HEAD"], text=True).strip(),
            "files": {x: hashlib.sha256((repo / x).read_bytes()).hexdigest() for x in tracked if (repo / x).is_file()},
        }
    manifest["sql2text"] = {p.name: len(read(p)) for p in (SOURCES / "ast-icl/s2t-datasets").glob("*.test.json")}
    manifest["scare"] = {p.name: len(read(p)) for p in (SOURCES / "SCARE/correction-data").glob("*.json")}
    manifest["clinsql"] = {"benchmark": sum(1 for _ in (SOURCES / "ClinSQL/data/benchmark").rglob("query_*.txt")),
                           "splits": {p.name: sum(1 for _ in p.rglob("query_*.txt")) for p in (SOURCES / "ClinSQL/data/splits").iterdir() if p.is_dir()},
                           "gold_execution_verified": False, "dialect": "BigQuery", "metric": "Rubric SQL Score / Execution Score"}
    base = SOURCES / "ehrsql-2024/data/mimic_iv"
    exports = ROOT / "datasets/ehrsql-2024"
    exports.mkdir(parents=True, exist_ok=True)
    for split in ("train", "valid", "test"):
        data = read(base / split / "data.json")
        labels = read(base / split / "label.json")
        answers = read(base / split / "answer.json")
        ids = [x["id"] for x in data["data"]]
        assert len(ids) == len(set(ids))
        assert set(ids) == set(labels) == set(answers)
        nulls = sum(v == "null" for v in labels.values())
        manifest["ehrsql_2024"][split] = {"version": data["version"], "total": len(ids), "answerable": len(ids)-nulls, "unanswerable": nulls}
        with (exports / (split + ".inputs.jsonl")).open("w", encoding="utf-8") as inputs, (exports / (split + ".gold.jsonl")).open("w", encoding="utf-8") as gold:
            for x in data["data"]:
                inputs.write(json.dumps(x, ensure_ascii=False) + "\n")
                gold.write(json.dumps({"id": x["id"], "gold_sql": labels[x["id"]], "gold_result": answers[x["id"]]}, ensure_ascii=False) + "\n")
    for variant in ("mimicsql_template", "mimicsql_natural", "mimicsql_natural_v2"):
        manifest["mimicsql"][variant] = {}
        for split in ("train", "dev", "test"):
            path = SOURCES / "TREQS/mimicsql_data" / variant / (split + ".json")
            rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
            manifest["mimicsql"][variant][split] = len(rows)
    sys.path.insert(0, str(SOURCES / "ehrsql-2024/scoring_program"))
    from postprocessing import post_process_sql
    from scoring_utils import process_answer
    con = sqlite3.connect("file:" + (base / "mimic_iv.sqlite").as_posix() + "?mode=ro", uri=True)
    con.execute("PRAGMA query_only=ON")
    tables = [x[0] for x in con.execute("SELECT name FROM sqlite_master WHERE type='table'")]
    manifest["ehrsql_2024"]["database"] = {"tables": tables, "size_bytes": (base / "mimic_iv.sqlite").stat().st_size}
    labels = read(base / "test/label.json")
    answers = read(base / "test/answer.json")
    errors, mismatches, timeouts = [], [], []
    checked = 0
    for key, sql in labels.items():
        if sql == "null":
            assert answers[key] == "null"
            continue
        deadline = time.monotonic() + 10
        con.set_progress_handler(lambda: int(time.monotonic() > deadline), 10000)
        try:
            result = con.execute(post_process_sql(sql)).fetchall()
            if process_answer(result) != process_answer(answers[key]):
                mismatches.append(key)
            checked += 1
        except sqlite3.OperationalError as exc:
            (timeouts if "interrupt" in str(exc).lower() else errors).append({"id": key, "error": str(exc)})
        if checked and checked % 100 == 0:
            print(f"Checked {checked} gold queries", flush=True)
    con.close()
    manifest["ehrsql_2024"]["test_gold_preflight"] = {"successfully_executed": checked, "errors": errors, "timeouts": timeouts, "stored_answer_mismatches": mismatches, "timeout_seconds_per_query": 10}
    source = read(ROOT.parent / "evaluate_results.json")
    manifest["local_evaluation"] = {"dataset_size": source["dataset_size"], "timestamp": source["timestamp"], "modes": {}}
    for mode, results in source["details"].items():
        nonempty = [r for r in results if not r["gold_empty"]]
        matches = sum(r["execution_match"] is True for r in nonempty)
        manifest["local_evaluation"]["modes"][mode] = {
            "reported_ex": source["metrics"][mode]["ex"],
            "matches": matches, "nonempty_gold_total": len(nonempty),
            "ex_counting_failed_predictions": 100 * matches / len(nonempty) if nonempty else None,
            "rate_limit_errors": sum("429" in (r["error"] or "") for r in results),
        }
    (ROOT / "benchmark_manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"preflight": manifest["ehrsql_2024"]["test_gold_preflight"], "local_evaluation": manifest["local_evaluation"]}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
