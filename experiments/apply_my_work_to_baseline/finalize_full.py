"""Rescore a COMPLETE test run in the same Docker runtime as the ProbGate audit."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
from settings import ROOT, WORKSPACE, BASELINE
from evaluate import evaluate


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-name", required=True)
    args = parser.parse_args()
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,79}", args.run_name):
        parser.error("Invalid run name")
    run = ROOT/"runs"/args.run_name
    report = evaluate(run)
    if report.get("split") != "test" or not report["full_benchmark_complete"]:
        raise ValueError("Full test set required: no padding or extrapolation is allowed")
    expected = {r["id"] for r in json.loads((BASELINE/"data/inputs/test.json").read_text())["data"]}
    export = BASELINE/"runs"/("apply_work_"+args.run_name)
    if not export.resolve().is_relative_to((BASELINE/"runs").resolve()):
        raise ValueError("Export outside expected baseline runs directory")
    export.mkdir(parents=True, exist_ok=True)
    comparison = {}
    paper = {"RS0":81.92, "RS5":78.06, "RS10":74.21, "RSN":-818.08}
    for mode in report["variants"]:
        source = run/(mode+".prediction.json")
        prediction = json.loads(source.read_text())
        if set(prediction) != expected:
            raise ValueError("Prediction IDs do not equal the full test split")
        directory = export/mode
        directory.mkdir(exist_ok=True)
        target = directory/"prediction.json"
        if target.exists() and target.read_bytes() != source.read_bytes():
            raise ValueError("Refusing to replace a different prediction artifact")
        target.write_bytes(source.read_bytes())
        relative = directory.relative_to(BASELINE).as_posix()
        if not (directory/"scores.json").exists():
            subprocess.run(["docker", "compose", "exec", "-T", "probgate-baseline", "python", "reproduce.py", "score",
                            "--split", "test", "--scorer", "official", "--predictions", relative+"/prediction.json",
                            "--output", relative+"/scores.json"], cwd=WORKSPACE, check=True)
        score = json.loads((directory/"scores.json").read_text())
        if score.get("prediction_sha256") != hashlib.sha256(source.read_bytes()).hexdigest() or score.get("scorer") != "official":
            raise ValueError("Scored artifact provenance does not match predictions/protocol")
        comparison[mode] = {"scores":score["scores"], "published_best":paper,
                            "delta_vs_published_best":{k:score["scores"][k]-paper[k] for k in paper}}
    (run/"final_docker_comparison.json").write_text(json.dumps(comparison, indent=2)+"\n")
    print(json.dumps(comparison, indent=2))


if __name__ == "__main__":
    main()

