"""Inspect the current V6 or replay its saved predictions without model/API calls."""
import argparse
import json
from pathlib import Path
from run_v6 import BASELINE, DEFAULT_RUN, frozen_check, load, score_mapping


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--verify-sql", action="store_true")
    args = parser.parse_args()
    result = load(DEFAULT_RUN / "FINAL_RESULTS.json")
    metric = result["SQL"]["V6_dev_selected"]
    verified = frozen_check()
    if args.verify_sql:
        predictions = load(DEFAULT_RUN / "test/V6_dev_selected.prediction.json")
        gold = load(BASELINE / "data/gold/test/answer.json")
        actual = score_mapping(predictions, gold, {})
        previous = load(DEFAULT_RUN / "test/evaluation.json")["systems"]["V6_dev_selected"]
        if actual["per_question"] != previous["per_question"] or actual["scores"] != previous["scores"]:
            raise ValueError("V6 replay no longer matches saved results")
    print(json.dumps({"current_system": "V6", "model": "deepseek-flash", "questions": 1167,
        "SQL": metric, "English": result["English"]["V6_dev_selected"],
        "provenance_files_verified": verified, "fresh_SQL_replay": args.verify_sql,
        "new_model_API_calls": 0}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
