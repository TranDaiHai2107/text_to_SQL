"""API adapter for the OpenAI reference rows in OmniSQL's BIRD dev experiment.

The paper does not release its proprietary API caller, so this adapter is an
explicit reconstruction. It uses the authors' exact preprocessed prompts
(``input_seq`` only, sent as a single user message like the authors' chat
template for open models), their SQL extraction rule (last ```sql fence),
their decoding settings (greedy: temperature 0, n=1; majority: temperature 0.8,
n=8) and their output limit (2048 tokens). It does not call the API without
--execute and an explicit --max-requests limit.

Paper Table 4 (BIRD dev EX, greedy / majority of 8):
  gpt-4o-mini-2024-07-18  58.8 / 61.5
  gpt-4o-2024-11-20       61.9 / 64.0
"""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
import os
from pathlib import Path
import re
import threading

from verify_assets import DATA, HERE, ROOT, sha256, verify

PAPER_EX = {"gpt-4o-mini-2024-07-18": {"greedy_search": 0.588, "major_voting": 0.615},
            "gpt-4o-2024-11-20": {"greedy_search": 0.619, "major_voting": 0.640}}
SQL_BLOCK = re.compile(r"```sql\s*(.*?)\s*```", re.DOTALL)
MAX_OUTPUT_TOKENS = 2048  # infer.py: max_output_len


def parse_sql(response: str) -> str:
    matches = SQL_BLOCK.findall(response)
    return matches[-1].strip() if matches else ""


def request_spec(input_seq: str, model: str, mode: str) -> dict:
    """Chat Completions arguments for one question. Only input_seq (never output_seq/gold) is sent."""
    n, temperature = (1, 0.0) if mode == "greedy_search" else (8, 0.8)
    return {"model": model, "messages": [{"role": "user", "content": input_seq}],
            "temperature": temperature, "n": n, "max_tokens": MAX_OUTPUT_TOKENS}


def text_sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def write_manifest(path: Path, model: str, mode: str, questions: int) -> dict:
    """Pin the run configuration; refuse to mix runs whose configuration differs."""
    spec = request_spec("", model, mode)
    lock = json.loads((HERE / "SOURCE_LOCK.json").read_text(encoding="utf-8"))
    manifest = {
        "scope": "reconstructed proprietary baseline adapter; author API code unavailable",
        "model": model, "mode": mode, "temperature": spec["temperature"], "n": spec["n"],
        "max_tokens": spec["max_tokens"],
        "max_tokens_source": "adapted from author's open-model infer.py; proprietary API setting unpublished",
        "questions": questions,
        "prompt_sha256": lock["omnisql_processed_prompt_sha256"],
        "bird_dev_json_sha256": lock["bird_dev_json_sha256"],
        "author_evaluator_sha256": lock["key_file_sha256"]["train_and_evaluate/evaluate_bird.py"],
    }
    adapter = sha256(Path(__file__))
    if path.exists():
        old = json.loads(path.read_text(encoding="utf-8"))
        changed = [key for key, value in manifest.items() if old.get(key) != value]
        if changed:
            raise ValueError(f"Existing run manifest differs in {changed}; use a new --output-dir")
        manifest["adapter_sha256_history"] = old.get("adapter_sha256_history", [])
    else:
        manifest["adapter_sha256_history"] = []
    if adapter not in manifest["adapter_sha256_history"]:
        manifest["adapter_sha256_history"].append(adapter)
    path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return manifest


def load_checkpoint(path: Path) -> dict[int, dict]:
    completed = {}
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            row = json.loads(line)
            index = row["row_index"]
            if index in completed:
                raise ValueError(f"Duplicate checkpoint row: {index}")
            completed[index] = row
    return completed


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", choices=sorted(PAPER_EX), default="gpt-4o-mini-2024-07-18")
    parser.add_argument("--mode", choices=("greedy_search", "major_voting"), required=True)
    parser.add_argument("--max-requests", type=int, default=0,
                        help="Maximum API calls this invocation may make; default 0")
    parser.add_argument("--workers", type=int, default=8, help="concurrent API requests")
    parser.add_argument("--execute", action="store_true", help="Actually call the API")
    parser.add_argument("--output-dir", type=Path)
    args = parser.parse_args()
    info = verify()
    prompts = json.loads((DATA / "omnisql_dev_bird.json").read_text(encoding="utf-8"))
    n, temperature = (1, 0.0) if args.mode == "greedy_search" else (8, 0.8)
    output_dir = (args.output_dir or ROOT / "results" / "omnisql" / args.model).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    checkpoint = output_dir / f"{args.mode}.jsonl"
    write_manifest(output_dir / f"{args.mode}_manifest.json", args.model, args.mode, len(prompts))
    completed = load_checkpoint(checkpoint)
    if any(i < 0 or i >= len(prompts) for i in completed):
        raise ValueError("Checkpoint contains invalid row IDs")
    if any("input_sha256" in row and row["input_sha256"] != text_sha256(prompts[i]["input_seq"])
           for i, row in completed.items()):
        raise ValueError("Checkpoint row was generated from a different prompt")
    if any(len(row.get("pred_sqls", [])) != n or row.get("model") != args.model for row in completed.values()):
        raise ValueError("Checkpoint mode or model differs from this run")
    todo = [i for i in range(len(prompts)) if i not in completed]
    budget = min(len(todo), args.max_requests) if args.execute else 0
    print(json.dumps({"model": args.model, "mode": args.mode, "questions": info["questions"],
                      "completed": len(completed), "remaining": len(todo),
                      "api_calls_this_run": budget}, indent=2), flush=True)
    if budget:
        from dotenv import load_dotenv
        from openai import OpenAI

        load_dotenv(ROOT / ".env", override=False)
        if not os.getenv("OPENAI_API_KEY"):
            raise RuntimeError("OPENAI_API_KEY is missing")
        client = OpenAI(timeout=180, max_retries=4)
        if client.models.retrieve(args.model).id != args.model:
            raise RuntimeError(f"Model snapshot {args.model} is not available")
        lock = threading.Lock()

        def call(index: int) -> None:
            # Only input_seq is sent. output_seq contains gold SQL and must
            # never be included in the model request.
            completion = client.chat.completions.create(
                **request_spec(prompts[index]["input_seq"], args.model, args.mode))
            responses = [choice.message.content or "" for choice in completion.choices]
            if len(responses) != n:
                raise RuntimeError(f"Row {index}: expected {n} responses; received {len(responses)}")
            row = {"row_index": index, "input_sha256": text_sha256(prompts[index]["input_seq"]),
                   "pred_sqls": [parse_sql(text) for text in responses],
                   "responses": responses, "model": args.model, "served_model": completion.model,
                   "finish_reasons": [choice.finish_reason for choice in completion.choices],
                   "system_fingerprint": completion.system_fingerprint,
                   "usage": completion.usage.model_dump() if completion.usage else None}
            with lock:
                with checkpoint.open("a", encoding="utf-8") as stream:
                    stream.write(json.dumps(row, ensure_ascii=False) + "\n")
                completed[index] = row
                if len(completed) % 50 == 0:
                    print(f"{len(completed)}/{len(prompts)}", flush=True)

        with ThreadPoolExecutor(max_workers=args.workers) as pool:
            for future in [pool.submit(call, i) for i in todo[:budget]]:
                future.result()
    if len(completed) == len(prompts):
        ordered = [completed[i] for i in range(len(prompts))]
        final = output_dir / f"{args.mode}.json"
        final.write_text(json.dumps(ordered, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        usage = [row["usage"] or {} for row in ordered]
        print(json.dumps({"full_prediction_file": str(final),
                          "prompt_tokens": sum(u.get("prompt_tokens", 0) for u in usage),
                          "completion_tokens": sum(u.get("completion_tokens", 0) for u in usage),
                          "truncated_responses": sum(r != "stop" for row in ordered
                                                     for r in row.get("finish_reasons", ["stop"])),
                          "paper_ex": PAPER_EX[args.model][args.mode]}, indent=2))
    else:
        print(f"Checkpoint: {checkpoint} ({len(completed)}/{len(prompts)})")


if __name__ == "__main__":
    main()
