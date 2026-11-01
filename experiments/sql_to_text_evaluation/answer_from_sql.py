"""Optional offline bridge: predicted SQL -> read-only results -> English text.

This is a common deterministic verbalizer, not an LLM English-generation test.
No reference answers or gold SQL are read here. Use predictions already produced
by a system; never substitute gold labels for end-to-end evaluation.
"""
from __future__ import annotations

import argparse
from pathlib import Path

try:
    from .common_io import DATABASE, HERE, jsonl, legacy, load, sha, write_jsonl
    from .reference_renderer import EXECUTION_ERROR_TEXT, render_answer
except ImportError:
    from common_io import DATABASE, HERE, jsonl, legacy, load, sha, write_jsonl
    from reference_renderer import EXECUTION_ERROR_TEXT, render_answer


def verbalize(sqls, inputs, *, database=DATABASE, timeout_s=30):
    ids = [row["id"] for row in inputs]
    if len(ids) != len(set(ids)) or set(ids) != set(sqls):
        raise ValueError("Prediction SQL IDs must cover input IDs exactly once")
    core = legacy()
    output = []
    for key in ids:
        sql = sqls[key]
        if not isinstance(sql, str):
            raise ValueError("SQL prediction must be text")
        record = {"id": key, "sql_prediction": sql, "verbalizer": "controlled_english_values_v1"}
        if sql == "null":
            record.update(output_text=render_answer(None, answerable=False), status="abstained")
        else:
            try:
                if not sql.strip():
                    raise ValueError("Empty statement is not valid SQL")
                executable = core.post_process_sql(sql)
                rows = core.execute_readonly(executable, database, timeout_s)
                record.update(output_text=render_answer(rows), status="executed", executed_sql=executable)
            except Exception as error:
                # Execution failure stays WRONG. It is never silently converted
                # into a gold-correct unanswerable response.
                record.update(output_text=EXECUTION_ERROR_TEXT, status="execution_error", error_type=type(error).__name__)
        output.append(record)
    return output


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sql-predictions", type=Path, required=True)
    parser.add_argument("--inputs", type=Path, default=HERE / "data/inputs/test.jsonl")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--sql-timeout", type=float, default=30)
    args = parser.parse_args()
    outputs = verbalize(load(args.sql_predictions), jsonl(args.inputs), timeout_s=args.sql_timeout)
    # All original artifacts remain untouched; caller chooses a NEW output file.
    for original in (args.sql_predictions, args.inputs, DATABASE):
        if args.output.resolve() == original.resolve():
            raise ValueError("Output must not overwrite an input/database")
    write_jsonl(args.output, outputs)
    print(f"Wrote {len(outputs)} deterministic English predictions; no model/API calls.")
