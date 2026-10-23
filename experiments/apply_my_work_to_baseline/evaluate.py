"""Score actual completed paired questions; never pad unfinished IDs with null."""
import argparse
from collections import Counter
import json
from pathlib import Path
import random
import sqlite3
from settings import ROOT, BASELINE, DB
from baseline_core import process_answer, score_answers, execute_readonly, post_process_sql


def paired_delta(reference, candidate, penalty=10):
    ids = list(reference)
    if set(ids) != set(candidate):
        raise ValueError("Paired comparison requires identical IDs")
    values = {"correct":1, "wrong":-penalty, "abstained_answerable":0}
    changes = [values[candidate[k]]-values[reference[k]] for k in ids]
    if not changes:
        return None
    rng = random.Random(42)
    draws = sorted(100*sum(rng.choices(changes, k=len(changes)))/len(changes) for _ in range(2000))
    return {"metric":"RS10", "n":len(changes), "delta_points":100*sum(changes)/len(changes),
            "paired_bootstrap_95_percent_interval":[draws[49], draws[1949]],
            "improved_questions":sum(v>0 for v in changes), "worsened_questions":sum(v<0 for v in changes)}


def evaluate(run_dir):
    run_dir = Path(run_dir)
    config = json.loads((run_dir/"config.json").read_text())
    records = [json.loads(line) for line in (run_dir/"records.jsonl").read_text().splitlines()] if (run_dir/"records.jsonl").exists() else []
    if not records:
        report = {"completed_questions":0, "full_benchmark_complete":False, "reason":"No complete paired question yet"}
        (run_dir/"evaluation.json").write_text(json.dumps(report, indent=2)+"\n")
        return report
    if len({r["id"] for r in records}) != len(records):
        raise ValueError("Duplicate question ID")
    gold = json.loads((BASELINE/"data/gold"/config["split"]/"answer.json").read_text())
    expected = 1167 if config["split"]=="test" else 1163
    ids = [r["id"] for r in records]
    selected_gold = {key:gold[key] for key in ids}
    variants = {}
    for mode in config["modes"]:
        predicted, errors = {}, []
        for row in records:
            record = row["variants"][mode]
            sql = record["sql"]
            if sql == "null":
                predicted[row["id"]] = "null"
            elif not record["execution"]["valid"] and not record.get("gef_filtered"):
                predicted[row["id"]] = "error_pred"
                errors.append({"id":row["id"], "error":record["execution"]["error"]})
            else:
                try:
                    predicted[row["id"]] = execute_readonly(post_process_sql(sql), DB, 30)
                except Exception as error:
                    predicted[row["id"]] = "error_pred"
                    errors.append({"id":row["id"], "error":str(error)})
        metrics = score_answers(selected_gold, predicted, scorer="official")
        answerable = [k for k in ids if gold[k] != "null"]
        matches = sum(metrics["per_question"][k]=="correct" for k in answerable)
        metrics["answerable_ex"] = 100*matches/len(answerable) if answerable else None
        metrics["answerable_ex_denominator"] = len(answerable)
        metrics["execution_errors"] = errors
        metrics["abstained"] = sum(v=="null" for v in predicted.values())
        metrics["sql_executed_successfully"] = sum(isinstance(v, list) for v in predicted.values())
        metrics["vsr_all_questions"] = 100*metrics["sql_executed_successfully"]/len(records)
        answered = len(records)-metrics["abstained"]
        metrics["execution_success_among_answered"] = 100*metrics["sql_executed_successfully"]/answered if answered else None
        variants[mode] = metrics
        # Complete output only for a complete split. No synthetic prediction for missing IDs.
        prediction = {row["id"]:row["variants"][mode]["sql"] for row in records}
        (run_dir/(mode+".prediction.json")).write_text(json.dumps(prediction, indent=2)+"\n")
    # Score the author's best cached predictions ON THE SAME IDs for paired diagnostics.
    baseline_path = BASELINE/"runs/audit_20261023_docker/test_gpt_probgate_425_gef/prediction.json"
    paired_baseline = None
    if config["split"] == "test" and baseline_path.is_file():
        raw = json.loads(baseline_path.read_text())
        results = {key:"null" if raw[key]=="null" else execute_readonly(raw[key], DB, 30) for key in ids}
        paired_baseline = score_answers(selected_gold, results, scorer="official")
    calls_path = run_dir/"api_events.jsonl"
    events = [json.loads(line) for line in calls_path.read_text().splitlines()] if calls_path.exists() else []
    success = [e for e in events if e["kind"]=="success"]
    report = {"split":config["split"], "completed_questions":len(records), "expected_questions":expected,
              "full_benchmark_complete":len(records)==expected, "official_normalization":True,
              "runtime_sqlite":sqlite3.sqlite_version, "variants":variants,
              "paired_author_best_on_same_ids":paired_baseline,
              "primary_variant":config.get("primary_variant"), "primary_metric":"RS10",
              "paired_deltas_vs_same_model_base":{
                  mode:paired_delta(variants["base"]["per_question"], metrics["per_question"])
                  for mode, metrics in variants.items() if mode != "base"} if "base" in variants else {},
              "all_successful_api_calls":len(success),
              "api_usage":{key:sum(e["usage"].get(key,0) or 0 for e in success)
                           for key in ["prompt_tokens", "completion_tokens", "total_tokens"]},
              "warning":None if len(records)==expected else "PARTIAL: paired diagnostics only; do not compare this sample to full-paper scores. RSN uses the current sample n."}
    if paired_baseline:
        report["paired_deltas_vs_author_cache"] = {mode:paired_delta(paired_baseline["per_question"], metrics["per_question"])
                                                   for mode, metrics in variants.items()}
    (run_dir/"evaluation.json").write_text(json.dumps(report, indent=2)+"\n", encoding="utf-8")
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-name", required=True)
    args = parser.parse_args()
    result = evaluate(ROOT/"runs"/args.run_name)
    print(json.dumps({k:v for k,v in result.items() if k not in {"variants", "paired_author_best_on_same_ids"}}, indent=2))
    for name, metrics in result.get("variants", {}).items():
        print(name, json.dumps(metrics["scores"]))

