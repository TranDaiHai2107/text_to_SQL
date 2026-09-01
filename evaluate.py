"""
Evaluate.py – Đánh giá hệ thống Text-to-SQL trên MIMIC-IV.

Đo lường 2 chỉ số:
  VSR  (Valid SQL Rate)       – % câu SQL chạy không bị lỗi syntax/runtime
  EX   (Execution Accuracy)  – % câu SQL cho kết quả khớp với gold SQL

Chạy ablation trên 5 mode:
  base      – prompt tĩnh, không RAG
  icd       – chỉ ICD retrieval
  schema    – chỉ schema retrieval
  examples  – chỉ example retrieval
  full      – đầy đủ 3 tầng RAG

Kết quả lưu vào evaluate_results.json và in bảng tổng kết ra terminal.
"""

import sys
import json
import time
import traceback

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
from datetime import datetime
from pathlib import Path

import pandas as pd
from sqlalchemy import text

from rag_engine import generate_sql, run_query, engine

MODES = ["base", "icd", "schema", "examples", "full"]
TEST_FILE = "test_dataset.json"
RESULTS_FILE = "evaluate_results.json"
DELAY_BETWEEN_CALLS = 1.5   # giây – tránh rate limit Groq


def load_test_dataset() -> list[dict]:
    with open(TEST_FILE, encoding="utf-8") as f:
        return json.load(f)


def normalize_df(df: pd.DataFrame) -> set:
    """
    Chuẩn hóa DataFrame thành tập frozenset các tuple để so sánh kết quả
    không phụ thuộc thứ tự cột và hàng.
    """
    if df is None or df.empty:
        return set()
    df = df.copy()
    df.columns = [str(c).lower().strip() for c in df.columns]
    df = df.applymap(lambda x: round(float(x), 4) if isinstance(x, float) else str(x).strip().lower())
    return {frozenset(row.items()) for _, row in df.iterrows()}


def run_gold_sql(gold_sql: str) -> pd.DataFrame | None:
    try:
        with engine.connect() as conn:
            return pd.read_sql(text(gold_sql), conn)
    except Exception:
        return None


def evaluate_one(question: str, gold_sql: str | None, mode: str) -> dict:
    result = {
        "mode": mode,
        "question": question,
        "generated_sql": None,
        "valid_sql": False,
        "execution_match": None,   # True/False/None (None nếu không có gold)
        "error": None,
        "latency_s": None,
    }

    t0 = time.time()
    try:
        sql, _ = generate_sql(question, mode)
        result["generated_sql"] = sql
        result["latency_s"] = round(time.time() - t0, 2)
    except Exception as e:
        result["error"] = f"LLM error: {e}"
        result["latency_s"] = round(time.time() - t0, 2)
        return result

    # ── Kiểm tra Valid SQL ─────────────────────────────────────
    try:
        df_pred = run_query(sql)
        result["valid_sql"] = True
    except Exception as e:
        result["valid_sql"] = False
        result["error"] = f"SQL exec error: {str(e)[:200]}"
        return result

    # ── Kiểm tra Execution Match (chỉ khi có gold SQL) ────────
    if gold_sql:
        df_gold = run_gold_sql(gold_sql)
        if df_gold is not None:
            pred_set = normalize_df(df_pred)
            gold_set = normalize_df(df_gold)
            result["execution_match"] = (pred_set == gold_set)
        else:
            result["execution_match"] = None   # gold SQL lỗi → bỏ qua

    return result


def compute_metrics(results: list[dict]) -> dict:
    total = len(results)
    vsr_count = sum(1 for r in results if r["valid_sql"])

    ex_eligible = [r for r in results if r["execution_match"] is not None]
    ex_count = sum(1 for r in ex_eligible if r["execution_match"])

    return {
        "total_questions": total,
        "vsr": round(vsr_count / total * 100, 1) if total else 0,
        "vsr_count": vsr_count,
        "ex": round(ex_count / len(ex_eligible) * 100, 1) if ex_eligible else None,
        "ex_count": ex_count,
        "ex_eligible": len(ex_eligible),
        "avg_latency_s": round(
            sum(r["latency_s"] for r in results if r["latency_s"]) / total, 2
        ) if total else 0,
    }


def print_summary(all_metrics: dict):
    print("\n" + "=" * 65)
    print("  ABLATION RESULTS SUMMARY")
    print("=" * 65)
    header = f"{'Mode':<12} {'VSR':>8} {'EX':>8} {'EX_n':>6} {'Latency':>10}"
    print(header)
    print("-" * 65)
    for mode, m in all_metrics.items():
        ex_str = f"{m['ex']:.1f}%" if m["ex"] is not None else "N/A"
        print(
            f"{mode:<12} {m['vsr']:>7.1f}%  {ex_str:>8}  "
            f"{m['ex_count']:>3}/{m['ex_eligible']:<3}  {m['avg_latency_s']:>8.2f}s"
        )
    print("=" * 65)


def run_evaluation(modes_to_run: list[str] | None = None, quick: bool = False):
    """
    modes_to_run: list mode muốn chạy; None = tất cả MODES
    quick: nếu True chỉ dùng 10 câu đầu để test nhanh
    """
    if modes_to_run is None:
        modes_to_run = MODES

    dataset = load_test_dataset()
    if quick:
        dataset = dataset[:10]
        print(f"[QUICK MODE] Chỉ chạy {len(dataset)} câu đầu.")

    print(f"Dataset: {len(dataset)} câu | Modes: {modes_to_run}")
    print(f"Bắt đầu: {datetime.now().strftime('%H:%M:%S')}\n")

    all_results = {}     # mode → list[dict]
    all_metrics = {}     # mode → metrics dict

    for mode in modes_to_run:
        print(f"\n{'─'*55}")
        print(f"  Mode: [{mode.upper()}]")
        print(f"{'─'*55}")
        mode_results = []

        for i, item in enumerate(dataset, 1):
            q = item["question_vi"]
            gold = item.get("gold_sql")
            print(f"  [{i:02d}/{len(dataset)}] {q[:60]}...", end=" ", flush=True)

            r = evaluate_one(q, gold, mode)
            mode_results.append(r)

            status = "✓" if r["valid_sql"] else "✗"
            ex_str = ""
            if r["execution_match"] is True:
                ex_str = " EX✓"
            elif r["execution_match"] is False:
                ex_str = " EX✗"
            print(f"{status}{ex_str}  ({r['latency_s']}s)")

            time.sleep(DELAY_BETWEEN_CALLS)

        all_results[mode] = mode_results
        all_metrics[mode] = compute_metrics(mode_results)

        m = all_metrics[mode]
        print(f"\n  → VSR={m['vsr']}%  EX={m['ex']}%  Latency={m['avg_latency_s']}s")

    # ── In bảng tổng kết ──────────────────────────────────────
    print_summary(all_metrics)

    # ── Lưu kết quả ───────────────────────────────────────────
    output = {
        "timestamp": datetime.now().isoformat(),
        "dataset_size": len(dataset),
        "metrics": all_metrics,
        "details": all_results,
    }
    with open(RESULTS_FILE, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"\nKết quả đã lưu: {RESULTS_FILE}")

    return all_metrics


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Evaluate MIMIC Text-to-SQL pipeline")
    parser.add_argument(
        "--modes", nargs="+", default=None,
        choices=MODES,
        help="Các mode muốn chạy (mặc định: tất cả)"
    )
    parser.add_argument(
        "--quick", action="store_true",
        help="Chỉ dùng 10 câu đầu để test nhanh"
    )
    args = parser.parse_args()

    run_evaluation(modes_to_run=args.modes, quick=args.quick)
