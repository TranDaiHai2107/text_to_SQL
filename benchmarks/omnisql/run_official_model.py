"""Run the authors' untouched OmniSQL inference and EX scorer on BIRD dev.

Requires Linux, CUDA, vLLM 0.6.3.post1 and enough GPU memory. Default is a
dry run; --execute launches the model.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
import sys

from verify_assets import DATA, HERE, ROOT, verify

MODELS = ("seeklhy/OmniSQL-7B", "seeklhy/OmniSQL-14B", "seeklhy/OmniSQL-32B")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", choices=MODELS, required=True)
    parser.add_argument("--mode", choices=("greedy_search", "major_voting"), required=True)
    parser.add_argument("--model-path", type=Path,
                        help="Local Hugging Face snapshot path pinned to SOURCE_LOCK.json revision")
    parser.add_argument("--tensor-parallel-size", type=int, default=2)
    parser.add_argument("--output-dir", type=Path, default=ROOT / "results" / "omnisql" / "official_model")
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()
    verify()
    lock = json.loads((HERE / "SOURCE_LOCK.json").read_text(encoding="utf-8"))
    revision = lock["huggingface_model_revisions"][args.model]
    if args.execute:
        if args.model_path is None or not args.model_path.is_dir() or revision not in args.model_path.resolve().parts:
            raise ValueError(f"Download {args.model} at revision {revision} to a Hugging Face snapshot path and pass --model-path")
    model_location = str(args.model_path.resolve()) if args.model_path else args.model
    n, temperature = (1, "0.0") if args.mode == "greedy_search" else (8, "0.8")
    output_dir = args.output_dir.resolve() / args.model.split("/")[-1]
    predictions = output_dir / f"{args.mode}.json"
    score = output_dir / f"{args.mode}_score.json"
    infer = [sys.executable, str(HERE / "official" / "train_and_evaluate" / "infer.py"),
             "--pretrained_model_name_or_path", model_location,
             "--input_file", str(DATA / "omnisql_dev_bird.json"),
             "--output_file", str(predictions),
             "--tensor_parallel_size", str(args.tensor_parallel_size),
             "--n", str(n), "--temperature", temperature]
    evaluate = [sys.executable, str(HERE / "score_bird.py"), str(predictions),
                "--mode", args.mode, "--output", str(score)]
    print(json.dumps({"model_revision": revision, "weights_pinned": args.model_path is not None,
                      "inference": infer, "evaluation": evaluate, "execute": args.execute}, indent=2))
    if args.execute:
        output_dir.mkdir(parents=True, exist_ok=True)
        subprocess.run(infer, check=True)
        subprocess.run(evaluate, check=True)


if __name__ == "__main__":
    main()
