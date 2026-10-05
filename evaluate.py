"""Evaluate the MIMIC-IV Text-to-SQL pipeline with leakage-safe retrieval."""

from __future__ import annotations

import argparse
import json
import sys
import time
from collections import Counter, defaultdict
from datetime import date, datetime
from decimal import Decimal
from numbers import Number
from typing import Any

import pandas as pd
from sqlalchemy.exc import OperationalError

from config import MAX_EVAL_ROWS, RESULTS_FILE, TEST_FILE
from rag_engine import generate_sql, generate_sql_with_correction, run_query


sys.stdout.reconfigure(encoding="utf-8", errors="replace")

MODES = ["base", "icd", "schema", "examples", "full", "full_agentic"]
DELAY_BETWEEN_CALLS = 1.5
EVAL_EXAMPLES_COLLECTION = "sql_examples_eval"


def load_test_dataset() -> list[dict[str, Any]]:
    with TEST_FILE.open(encoding="utf-8") as handle:
        return json.load(handle)


def _normalize_value(value: Any) -> tuple[str, str]:
    """Create a deterministic, JSON-safe scalar representation."""
    try:
        if pd.isna(value):
            return ("null", "")
    except (TypeError, ValueError):
        pass

    if isinstance(value, bool):
        return ("bool", "1" if value else "0")
    if isinstance(value, Number) and not isinstance(value, bool):
        numeric = Decimal(str(value))
        if not numeric.is_finite():
            return ("number", str(numeric).lower())
        normalized = numeric.quantize(Decimal("0.000001")).normalize()
        return ("number", format(normalized, "f"))
    if isinstance(value, (datetime, date, pd.Timestamp)):
        return ("datetime", pd.Timestamp(value).isoformat())
    return ("text", str(value).strip().casefold())


def normalize_df(df: pd.DataFrame) -> Counter:
    """Compare row multisets while ignoring row order and output aliases."""
    rows = []
    for row in df.itertuples(index=False, name=None):
        normalized = tuple(sorted((_normalize_value(value) for value in row)))
        rows.append(normalized)
    return Counter(rows)


def preflight_gold(dataset: list[dict[str, Any]]) -> dict[str, pd.DataFrame]:
    """Run every gold query before spending any LLM calls."""
    cache: dict[str, pd.DataFrame] = {}
    failures: list[str] = []
    for item in dataset:
        gold_sql = item.get("gold_sql")
        if not gold_sql:
            failures.append(f"{item['id']}: thiếu gold_sql")
            continue
        try:
            cache[item["id"]] = run_query(gold_sql, max_rows=MAX_EVAL_ROWS)
        except OperationalError as exc:
            raise RuntimeError(
                "Không kết nối được PostgreSQL trong gold preflight. Kiểm tra Docker và cấu hình DB."
            ) from exc
        except Exception as exc:
            failures.append(f"{item['id']}: {str(exc).splitlines()[0]}")

    if failures:
        details = "\n".join(f"- {failure}" for failure in failures)
        raise RuntimeError(
            f"Gold SQL preflight thất bại ({len(failures)} câu). Sửa dataset trước khi đánh giá:\n{details}"
        )
    return cache


def evaluate_one(
    item: dict[str, Any],
    mode: str,
    gold_df: pd.DataFrame,
) -> dict[str, Any]:
    result: dict[str, Any] = {
        "id": item["id"],
        "mode": mode,
        "difficulty": item.get("difficulty", "unknown"),
        "question": item["question_vi"],
        "generated_sql": None,
        "valid_sql": False,
        "execution_match": None,
        "gold_empty": gold_df.empty,
        "error": None,
        "latency_s": None,
        "attempts": 1,
    }
    started = time.perf_counter()

    try:
        if mode == "full_agentic":
            agentic = generate_sql_with_correction(
                item["question_vi"],
                mode="full",
                max_retries=2,
                examples_collection=EVAL_EXAMPLES_COLLECTION,
                query_max_rows=MAX_EVAL_ROWS,
            )
            result["generated_sql"] = agentic["sql"]
            result["attempts"] = agentic["attempts"]
            if not agentic["success"]:
                last_error = agentic["history"][-1]["error"] if agentic["history"] else "Unknown"
                result["error"] = f"Agentic failed: {str(last_error)[:300]}"
                return result
            predicted_df = agentic["df"]
        else:
            sql, _ = generate_sql(
                item["question_vi"],
                mode,
                examples_collection=EVAL_EXAMPLES_COLLECTION,
            )
            result["generated_sql"] = sql
            predicted_df = run_query(sql, max_rows=MAX_EVAL_ROWS)

        result["valid_sql"] = True
        # An empty gold result does not prove semantic equivalence, so it is
        # reported separately and excluded from EX.
        if not gold_df.empty:
            result["execution_match"] = normalize_df(predicted_df) == normalize_df(gold_df)
        return result
    except Exception as exc:
        result["error"] = f"{type(exc).__name__}: {str(exc)[:300]}"
        return result
    finally:
        result["latency_s"] = round(time.perf_counter() - started, 3)


def compute_metrics(results: list[dict[str, Any]]) -> dict[str, Any]:
    total = len(results)
    valid_count = sum(bool(result["valid_sql"]) for result in results)
    eligible = [result for result in results if result["execution_match"] is not None]
    matches = sum(result["execution_match"] is True for result in eligible)
    latencies = [result["latency_s"] for result in results if result["latency_s"] is not None]
    return {
        "total_questions": total,
        "vsr": round(valid_count / total * 100, 1) if total else 0.0,
        "vsr_count": valid_count,
        "ex": round(matches / len(eligible) * 100, 1) if eligible else None,
        "ex_count": matches,
        "ex_eligible": len(eligible),
        "empty_gold": sum(bool(result["gold_empty"]) for result in results),
        "avg_latency_s": round(sum(latencies) / len(latencies), 3) if latencies else 0.0,
    }


def metrics_by_difficulty(results: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for result in results:
        groups[result["difficulty"]].append(result)
    return {difficulty: compute_metrics(rows) for difficulty, rows in sorted(groups.items())}


def print_summary(all_metrics: dict[str, dict[str, Any]]) -> None:
    print("\n" + "=" * 76)
    print("  ABLATION RESULTS SUMMARY")
    print("=" * 76)
    print(f"{'Mode':<14} {'VSR':>8} {'EX':>8} {'EX_n':>9} {'Empty':>7} {'Latency':>10}")
    print("-" * 76)
    for mode, metrics in all_metrics.items():
        ex_text = f"{metrics['ex']:.1f}%" if metrics["ex"] is not None else "N/A"
        print(
            f"{mode:<14} {metrics['vsr']:>7.1f}% {ex_text:>8} "
            f"{metrics['ex_count']:>3}/{metrics['ex_eligible']:<5} "
            f"{metrics['empty_gold']:>7} {metrics['avg_latency_s']:>8.3f}s"
        )
    print("=" * 76)


def run_evaluation(modes_to_run: list[str] | None = None, quick: bool = False):
    modes = modes_to_run or MODES
    dataset = load_test_dataset()
    if quick:
        dataset = dataset[:10]
        print(f"[QUICK MODE] Chỉ chạy {len(dataset)} câu đầu.")

    print(f"Preflight {len(dataset)} gold SQL...")
    gold_cache = preflight_gold(dataset)
    print(f"Dataset: {len(dataset)} câu | Modes: {modes}")

    all_results: dict[str, list[dict[str, Any]]] = {}
    all_metrics: dict[str, dict[str, Any]] = {}
    all_difficulty_metrics: dict[str, dict[str, dict[str, Any]]] = {}

    for mode in modes:
        print(f"\n{'─' * 55}\n  Mode: [{mode.upper()}]\n{'─' * 55}")
        mode_results = []
        for index, item in enumerate(dataset, 1):
            print(f"  [{index:03d}/{len(dataset)}] {item['question_vi'][:58]}... ", end="", flush=True)
            result = evaluate_one(item, mode, gold_cache[item["id"]])
            mode_results.append(result)
            status = "✓" if result["valid_sql"] else "✗"
            ex_status = " EX✓" if result["execution_match"] is True else " EX✗" if result["execution_match"] is False else ""
            print(f"{status}{ex_status} ({result['latency_s']}s)")
            if index < len(dataset):
                time.sleep(DELAY_BETWEEN_CALLS)

        all_results[mode] = mode_results
        all_metrics[mode] = compute_metrics(mode_results)
        all_difficulty_metrics[mode] = metrics_by_difficulty(mode_results)

    print_summary(all_metrics)
    output = {
        "timestamp": datetime.now().isoformat(),
        "dataset_size": len(dataset),
        "examples_collection": EVAL_EXAMPLES_COLLECTION,
        "metrics": all_metrics,
        "metrics_by_difficulty": all_difficulty_metrics,
        "details": all_results,
    }
    with RESULTS_FILE.open("w", encoding="utf-8") as handle:
        json.dump(output, handle, ensure_ascii=False, indent=2)
    print(f"\nKết quả đã lưu: {RESULTS_FILE}")
    return all_metrics


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Evaluate MIMIC Text-to-SQL pipeline")
    parser.add_argument("--modes", nargs="+", choices=MODES)
    parser.add_argument("--quick", action="store_true", help="Chỉ dùng 10 câu đầu")
    args = parser.parse_args()
    try:
        run_evaluation(modes_to_run=args.modes, quick=args.quick)
    except RuntimeError as exc:
        parser.exit(1, f"Lỗi: {exc}\n")
