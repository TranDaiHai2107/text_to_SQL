"""Read-only comparison of application data and pinned ProbGate benchmark.

Does not run benchmark SQL, inference, or alter either database.
--inspect-postgres optionally reads local metadata/counts using application config.
No credentials or patient identifiers are written to the report.
"""
from __future__ import annotations

import argparse
from collections import Counter
import json
from pathlib import Path
import re
import sqlite3
import sys

ROOT = Path(__file__).resolve().parents[1]
WORKSPACE = ROOT.parents[1]


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--inspect-postgres", action="store_true")
    args = parser.parse_args()
    schema = read(WORKSPACE / "mimic_schema.json")
    questions = read(WORKSPACE / "test_dataset.json")
    examples = read(WORKSPACE / "mimic_examples.json")
    manifest = read(ROOT / "source_manifest.json")
    from sqlglot import exp, parse_one
    columns = {row["table"]: [node.name for node in parse_one(row["ddl"], read="postgres").find_all(exp.ColumnDef)] for row in schema}
    normal_sql = lambda s: parse_one(s, read="postgres").sql(dialect="postgres")
    gold_sql = {normal_sql(row["gold_sql"]) for row in questions}
    overlaps = [row["id"] for row in examples if normal_sql(row["sql"]) in gold_sql]
    connection = sqlite3.connect((ROOT / manifest["database_path"]).resolve().as_uri() + "?mode=ro", uri=True)
    try:
        connection.execute("PRAGMA query_only=ON")
        tables = [row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")]
        benchmark_columns = {table: [row[1] for row in connection.execute("PRAGMA table_info(" + table + ")")] for table in tables}
        benchmark_patients = {row[0] for row in connection.execute("SELECT subject_id FROM patients")}
        counts = {table: connection.execute('SELECT COUNT(*) FROM "' + table + '"').fetchone()[0] for table in tables}
    finally:
        connection.close()
    report = {"checked_on": "2026-10-19", "scope": "metadata, counts, split and schema compatibility; no model/evaluation execution",
        "application": {"schema_tables": len(schema), "table_names": sorted(columns),
            "question_count": len(questions), "question_fields": sorted(questions[0]),
            "english_question_fields_present": any("question_en" in r for r in questions),
            "unanswerable_gold_count": sum(row.get("gold_sql") in (None, "", "null") for row in questions),
            "difficulties": dict(Counter(row.get("difficulty") for row in questions)),
            "example_count": len(examples), "example_ids_with_exact_canonical_sql_overlap": overlaps,
            "source_version_directory": "mimic-iv-3.1", "configured_default_patients": 500,
            "sampling_uses_test_gold_icd": "((TEST_FILE, \"gold_sql\"), (EXAMPLES_FILE, \"sql\"))" in (WORKSPACE / "build_mimic_mini.py").read_text(encoding="utf-8")},
        "benchmark": {"database_path": manifest["database_path"], "tables": tables, "table_count": len(tables),
            "row_counts": counts, "patient_count": len(benchmark_patients), "splits": manifest["splits"]},
        "schema_difference": {"benchmark_only_tables": sorted(set(tables)-set(columns)),
            "application_only_tables": sorted(set(columns)-set(tables)),
            "benchmark_columns_absent_in_application": {t: sorted(set(benchmark_columns[t])-set(columns[t])) for t in tables if t in columns and set(benchmark_columns[t])-set(columns[t])}},
        "live_postgres": {"inspected": False, "reason": "not requested"},
        "recommendation": {"keep_current_dataset_for": "application development and internal/Vietnamese/multi-turn evaluation",
            "use_probgate_dataset_for": "all direct numerical comparisons to ProbGate",
            "replace_production_database": False,
            "direct_comparison_using_current_180_questions": False}}
    if args.inspect_postgres:
        engine = None
        try:
            sys.path.insert(0, str(WORKSPACE))
            from config import database_url
            from sqlalchemy import create_engine, text
            engine = create_engine(database_url(), connect_args={"connect_timeout": 3})
            with engine.connect().execution_options(postgresql_readonly=True) as con:
                with con.begin():
                    con.execute(text("SET LOCAL statement_timeout = 5000"))
                    live_tables = list(con.execute(text("SELECT table_name FROM information_schema.tables WHERE table_schema='public' AND table_type='BASE TABLE' ORDER BY table_name")).scalars())
                    live_columns = list(con.execute(text("SELECT table_name, column_name FROM information_schema.columns WHERE table_schema='public' ORDER BY table_name,ordinal_position")))
                    live_counts = {t: con.execute(text('SELECT COUNT(*) FROM "' + t.replace('"', '""') + '"')).scalar_one() for t in live_tables}
                    live_patients = set(con.execute(text("SELECT subject_id FROM patients")).scalars())
            report["live_postgres"] = {"inspected": True, "table_count": len(live_tables), "row_counts": live_counts,
                "total_rows_across_tables": sum(live_counts.values()), "patient_count": len(live_patients),
                "benchmark_patient_id_overlap_count": len(live_patients & benchmark_patients),
                "columns": {t: [r[1] for r in live_columns if r[0] == t] for t in live_tables}}
        except Exception as error:
            report["live_postgres"] = {"inspected": False, "attempted": True, "error_type": type(error).__name__,
                "reason": "Could not complete read-only local inspection; declared schema/loader settings are not proof of live database contents."}
        finally:
            if engine is not None:
                engine.dispose()
    (ROOT / "DATASET_AUDIT.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"application_questions": len(questions), "application_tables": len(schema),
        "benchmark_tables": len(tables), "benchmark_patient_count": len(benchmark_patients),
        "benchmark_total_rows": sum(counts.values()), "benchmark_only_tables": report["schema_difference"]["benchmark_only_tables"],
        "example_overlap_count": len(overlaps), "live_postgres": {k:v for k,v in report["live_postgres"].items() if k not in {"columns", "row_counts"}},
        "recommendation": report["recommendation"]}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
