"""Audit published M3 artifacts offline; no inference, no database writes.

Run with the bundled Python (numpy needed by upstream scoring_utils).
Exports holdout inputs separately from gold and published model outputs.
"""
from __future__ import annotations

import csv
import hashlib
import json
import math
from collections import Counter, defaultdict
from pathlib import Path
import re
import sqlite3
import subprocess
import sys
import time
import unicodedata

ROOT = Path(__file__).resolve().parent
SOURCES = ROOT / "sources"
M3 = SOURCES / "m3"
EHR = SOURCES / "ehrsql-2024"
BENCH = M3 / "benchmarks/ehrsql-naacl2024"
OUT = ROOT / "datasets/m3-ehrsql-2024"
HISTORICAL_REV = "2cf205a"


def historical_file(relative):
    return subprocess.check_output(["git", "-C", str(EHR), "show", HISTORICAL_REV + ":" + relative])


def read_json(p):
    return json.loads(p.read_text(encoding="utf-8"))


def csv_rows(p):
    with p.open(encoding="utf-8-sig", newline="") as handle:
        return [{k.strip(): v for k, v in r.items()} for r in csv.DictReader(handle)]


def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def normalize_space(s):
    return " ".join(unicodedata.normalize("NFKC", s).split())


def walk(x):
    if isinstance(x, dict):
        yield x
        for value in x.values():
            yield from walk(value)
    elif isinstance(x, list):
        for value in x:
            yield from walk(value)


def wilson(k, n):
    z = 1.959963984540054
    p = k/n
    denominator = 1 + z*z/n
    center = (p+z*z/(2*n))/denominator
    half = z*math.sqrt(p*(1-p)/n+z*z/(4*n*n))/denominator
    return [round(100*(center-half), 3), round(100*(center+half), 3)]


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    latest_base = EHR / "data/mimic_iv"
    base = SOURCES / "ehrsql-m3-v1.0.5"
    (base / "test").mkdir(parents=True, exist_ok=True)
    for name in ["test/data.json", "test/label.json", "test/answer.json", "mimic_iv.sqlite"]:
        (base / name).write_bytes(historical_file("data/mimic_iv/" + name))
    questions = read_json(base / "test/data.json")
    gold_sql = read_json(base / "test/label.json")
    gold_answer = read_json(base / "test/answer.json")
    qids = defaultdict(list)
    for r in questions["data"]:
        qids[r["question"]].append(r["id"])

    paths = {
        "claude": BENCH / "claude-sonnet-4/EHRSQL_benchmark.csv",
        "gpt_oss": BENCH / "gpt-oss-20B/EHRSQL_benchmark.csv",
        "unanswerable": BENCH / "gpt-oss-20B/EHRSQL_benchmark_unanswerable.csv",
    }
    data = {key: csv_rows(path) for key, path in paths.items()}
    supplements = {"claude": "s001", "gpt_oss": "s002", "unanswerable": "s003"}
    manifest = {
        "checked_on": "2026-10-12",
        "m3_commit": subprocess.check_output(["git", "-C", str(M3), "rev-parse", "HEAD"], text=True).strip(),
        "ehrsql_commit": subprocess.check_output(["git", "-C", str(EHR), "rev-parse", "HEAD"], text=True).strip(),
        "ehrsql_test_version": questions["version"],
        "ehrsql_historical_commit": subprocess.check_output(["git", "-C", str(EHR), "rev-parse", HISTORICAL_REV], text=True).strip(),
        "historical_vs_latest_database_same_hash": sha(base / "mimic_iv.sqlite") == sha(latest_base / "mimic_iv.sqlite"),
        "database_sha256": sha(base / "mimic_iv.sqlite"),
        "snapshot_hashes": {str(p.relative_to(SOURCES)).replace("\\", "/"): sha(p) for p in paths.values()},
        "groups": {},
        "inference_run": False,
        "benchmark_database_modified": False,
    }
    for group, rows in data.items():
        supplement = SOURCES / ("m3-plos-" + supplements[group] + ".csv")
        pub_rows = csv_rows(supplement)
        mapping = []
        for index, row in enumerate(rows, 1):
            ids = qids[row["Query"]]
            assert len(ids) == 1, (group, index, ids)
            key = ids[0]
            assert (gold_sql[key] == "null") == (group == "unanswerable")
            mapping.append(key)
        pub_by_question = {r["Query"]: r for r in pub_rows}
        differences = []
        normalized_differences = []
        for index, row in enumerate(rows, 1):
            pub = pub_by_question.get(row["Query"])
            if pub != row:
                differences.append({"index": index, "id": mapping[index-1], "fields": [k for k in row if pub is None or row[k] != pub.get(k)]})
            if pub is None or any(normalize_space(row[k]) != normalize_space(pub.get(k, "")) for k in row):
                normalized_differences.append(index)
        labels = Counter(row["Correct/Incorrect"] for row in rows)
        manifest["groups"][group] = {
            "total": len(rows), "unique_questions": len(set(mapping)),
            "matched_official_test_ids": len(mapping),
            "label_counts": dict(labels), "accuracy_percent": 100*labels["1"]/len(rows),
            "wilson_95_ci_percent": wilson(labels["1"], len(rows)),
            "published_supplement_sha256": sha(supplement),
            "supplement_raw_csv_differences": differences,
            "supplement_differences_after_normalizing_unicode_and_whitespace": normalized_differences,
            "ids": mapping,
            "wrong_notes": [{"id": mapping[i], "note": row["Incorrect Note"]} for i, row in enumerate(rows) if row["Correct/Incorrect"] == "0"],
        }

    cq = {r["Query"]: r for r in data["claude"]}
    gq = {r["Query"]: r for r in data["gpt_oss"]}
    assert set(cq) == set(gq)
    pairs = Counter((cq[q]["Correct/Incorrect"], gq[q]["Correct/Incorrect"]) for q in cq)
    manifest["paired_outcomes"] = {"both_correct": pairs["1", "1"], "claude_only_correct": pairs["1", "0"], "gpt_only_correct": pairs["0", "1"], "both_wrong": pairs["0", "0"]}
    latest_questions = {r["id"]: r["question"] for r in read_json(latest_base / "test/data.json")["data"]}
    latest_sql = read_json(latest_base / "test/label.json")
    manifest["historical_vs_latest_sample_changes"] = [{"id": key,
        "m3_question": row["Query"], "latest_question": latest_questions.get(key),
        "sql_changed": gold_sql[key] != latest_sql.get(key)}
        for key, row in zip(manifest["groups"]["claude"]["ids"], data["claude"])
        if row["Query"] != latest_questions.get(key) or gold_sql[key] != latest_sql.get(key)]

    sys.path.insert(0, str(EHR / "scoring_program"))
    from postprocessing import post_process_sql
    from scoring_utils import process_answer
    con = sqlite3.connect("file:" + (base / "mimic_iv.sqlite").as_posix() + "?mode=ro", uri=True)
    con.execute("PRAGMA query_only=ON")
    tables = [row[0] for row in con.execute("SELECT name FROM sqlite_master WHERE type='table'")]
    manifest["database_profile"] = {
        "tables": tables,
        "patient_count": con.execute("SELECT COUNT(*) FROM patients").fetchone()[0],
        "columns": {table: [row[1] for row in con.execute("PRAGMA table_info(" + table + ")")] for table in tables},
        "icd_code_examples": [r[0] for r in con.execute("SELECT icd_code FROM diagnoses_icd LIMIT 3")],
    }
    gold_checks = []
    for i, row in enumerate(data["claude"]):
        key = manifest["groups"]["claude"]["ids"][i]
        deadline = time.monotonic() + 10
        con.set_progress_handler(lambda: int(time.monotonic() > deadline), 10000)
        try:
            result = con.execute(post_process_sql(row["Golden Truth SQL Query"])).fetchall()
            official_result = con.execute(post_process_sql(gold_sql[key])).fetchall()
            gold_checks.append({"id": key, "executes": True,
                "csv_sql_matches_official_execution": process_answer(result) == process_answer(official_result),
                "matches_official_stored_answer": process_answer(result) == process_answer(gold_answer[key]),
                "rows": len(result), "columns": len(result[0]) if result else None})
        except Exception as error:
            gold_checks.append({"id": key, "executes": False, "error": str(error)})
    con.close()
    manifest["gold_preflight"] = gold_checks
    manifest["gold_preflight_summary"] = {"total": len(gold_checks), "executed": sum(r["executes"] for r in gold_checks),
        "matches_official_execution": sum(r.get("csv_sql_matches_official_execution", False) for r in gold_checks),
        "matches_official_stored_answer": sum(r.get("matches_official_stored_answer", False) for r in gold_checks)}

    transcript_summary = {}
    for group in ("gpt_oss", "unanswerable"):
        details = []
        for index, row in enumerate(data[group]):
            rel = row["Chat Conversation"]
            p = BENCH / "gpt-oss-20B" / rel
            if not p.is_file():
                p = BENCH / "gpt-oss-20B/conversations" / rel
            assert p.is_file(), p
            transcript = read_json(p)
            calls = [x for message in transcript.get("messages", []) for x in walk(message) if x.get("type") == "toolCallRequest"]
            if "messages" not in transcript:
                calls = [{"name": x.get("tool"), "parameters": x.get("arguments")} for x in transcript.get("tool_calls", [])]
            sql_calls = [x for x in calls if x.get("name") == "execute_mimic_query"]
            configs = [(x.get("key"), x.get("value")) for x in walk(transcript) if x.get("key") in {"llm.prediction.temperature", "llm.prediction.seed", "llm.load.contextLength"}]
            user_text = [x["text"] for m in transcript.get("messages", []) for v in m.get("versions", []) if v.get("role") == "user" for x in v.get("content", []) if x.get("type") == "text"]
            if "prompt_sent" in transcript:
                user_text = [transcript["prompt_sent"]]
            details.append({"id": manifest["groups"][group]["ids"][index], "path": str(p.relative_to(M3)).replace("\\", "/"),
                "sha256": sha(p), "user_turns": len(user_text), "extra_user_prompts": user_text[1:], "tool_calls": len(calls), "sql_calls": len(sql_calls),
                "last_sql_call": sql_calls[-1].get("parameters") if sql_calls else None,
                "format": "lm_studio_export" if "messages" in transcript else "evaluation_export",
                "auto_classification": transcript.get("auto_classification"), "error": transcript.get("error"),
                "generation_settings": sorted({(k, json.dumps(v)) for k, v in configs})})
        transcript_summary[group] = {"count": len(details), "min_sql_calls": min(r["sql_calls"] for r in details),
            "max_sql_calls": max(r["sql_calls"] for r in details), "total_sql_calls": sum(r["sql_calls"] for r in details),
            "user_turn_histogram": dict(Counter(r["user_turns"] for r in details)),
            "settings": sorted({tuple(x) for r in details for x in r["generation_settings"]}), "details": details}
    manifest["transcripts"] = transcript_summary

    for group in ("answerable", "unanswerable"):
        source = "claude" if group == "answerable" else "unanswerable"
        with (OUT / (group + ".inputs.jsonl")).open("w", encoding="utf-8") as inp, (OUT / (group + ".gold.jsonl")).open("w", encoding="utf-8") as gold:
            for index, row in enumerate(data[source]):
                key = manifest["groups"][source]["ids"][index]
                inp.write(json.dumps({"id": key, "question": row["Query"]}, ensure_ascii=False) + "\n")
                record = {"id": key, "gold_sql": gold_sql[key], "gold_result": gold_answer[key],
                    "m3_gold_display": row["Golden Truth"], "answerable": group == "answerable", "published_baselines": {}}
                for model in (["claude", "gpt_oss"] if group == "answerable" else ["unanswerable"]):
                    other = (cq if model == "claude" else gq).get(row["Query"]) if model != "unanswerable" else row
                    record["published_baselines"][model] = {"answer": other["Model Answer"], "correct": other["Correct/Incorrect"] == "1", "note": other["Incorrect Note"], "conversation": other["Chat Conversation"]}
                gold.write(json.dumps(record, ensure_ascii=False) + "\n")

    manifest["first_case_warning"] = {"id": manifest["groups"]["claude"]["ids"][0],
        "question": data["claude"][0]["Query"], "gold_display_entries": len(data["claude"][0]["Golden Truth"].split(";")),
        "published_correct_labels": [cq[data["claude"][0]["Query"]]["Correct/Incorrect"], gq[data["claude"][0]["Query"]]["Correct/Incorrect"]],
        "interpretation": "Gold lists 23 drugs; published answers list 5, both labeled correct. Human semantic accuracy is not strict execution equivalence. This is an audit flag, not a complete re-adjudication."}
    (ROOT / "m3_audit_manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"commit": manifest["m3_commit"], "groups": {k: {x: v[x] for x in ["total", "matched_official_test_ids", "label_counts", "supplement_differences_after_normalizing_unicode_and_whitespace"]} for k, v in manifest["groups"].items()},
        "pairs": manifest["paired_outcomes"], "gold": manifest["gold_preflight_summary"],
        "database_unchanged_between_versions": manifest["historical_vs_latest_database_same_hash"], "sample_items_changed_since_v1_0_5": len(manifest["historical_vs_latest_sample_changes"]),
        "transcripts": {k: {x:v[x] for x in ["count", "min_sql_calls", "max_sql_calls", "total_sql_calls", "user_turn_histogram", "settings"]} for k,v in transcript_summary.items()}, "first_case": manifest["first_case_warning"]}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
