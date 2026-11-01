"""Finish both English chains and the renderer oracle after frozen SQL testing."""
from pathlib import Path

from english_evaluation import evaluate
from report_v6 import report
from run_v6 import DEFAULT_RUN, load, sha


def main():
    run = DEFAULT_RUN
    completion = load(run / "TEST_COMPLETE.json")
    if completion["evaluation_sha256"] != sha(run / "test/evaluation.json"):
        raise ValueError("Full SQL test artifacts changed")
    if completion["policy_sha256"] != sha(run / "policy.json"):
        raise ValueError("Policy changed after the full SQL test")
    for name in ("V5_frozen", "V6_dev_selected", "oracle_renderer"):
        destination = run / "english" / name
        if (destination / "ENGLISH_EVALUATION.json").exists():
            previous = load(destination / "ENGLISH_EVALUATION.json")
            if (previous["state"] != "complete" or previous["questions"] != 1167
                    or previous["English_prediction_sha256"] != sha(destination / "english_predictions.jsonl")
                    or previous["scores_sha256"] != sha(destination / "english_scores.json")):
                raise ValueError("Existing English output is incomplete or changed")
            print(name, "already complete; retaining predictions and scores", flush=True)
            continue
        kwargs = {"output_dir": destination, "split": "test", "timeout_s": 120}
        if name == "oracle_renderer":
            kwargs["mode"] = "oracle_renderer"
        else:
            kwargs["sql_predictions"] = run / "test" / (name + ".prediction.json")
        print("English evaluation starting:", name, flush=True)
        result = evaluate(**kwargs)
        print(name, "complete", result["questions"], "fact_EM", result["controlled"]["fact_EM"],
              "WER", result["lexical"]["WER"], flush=True)
    report(run)


if __name__ == "__main__":
    main()
