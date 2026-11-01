"""Build all English reference answers in a separate, fully traceable overlay."""
from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

try:
    from .common_io import BASELINE, DATABASE, HERE, SPLITS, WORKSPACE, dump, legacy, load, sha, verify_frozen, write_jsonl
    from .reference_renderer import RENDERER_VERSION, canonical_rows, parse_controlled_answer, render_answer
except ImportError:
    from common_io import BASELINE, DATABASE, HERE, SPLITS, WORKSPACE, dump, legacy, load, sha, verify_frozen, write_jsonl
    from reference_renderer import RENDERER_VERSION, canonical_rows, parse_controlled_answer, render_answer


def build(destination, timeout_s=120):
    destination = Path(destination)
    frozen_count = verify_frozen()
    core = legacy()
    files = {str(DATABASE.relative_to(WORKSPACE)): sha(DATABASE)}
    manifest = {"schema_version": 1, "dataset_name": "EHRSQL2024-derived-controlled-English-v1",
                "annotation_method": RENDERER_VERSION, "official_English_benchmark": False,
                "human_or_clinician_validated": False, "new_API_calls": 0,
                "clock": "2100-12-31 23:59:00", "numeric_precision_decimals": 3,
                "text_result_row_cap": None, "official_SQL_scoring_row_cap": 100,
                "row_order": "canonical unordered rows; duplicates and column order retained",
                "use": "Reference/evaluation only; test labels must never enter retrieval or prompts",
                "claim": "Mechanically faithful to executed gold query results, not verified clinical interpretation",
                "frozen_original_files_verified": frozen_count, "splits": {}}
    cache = {}
    for split, original in SPLITS.items():
        paths = {"inputs": BASELINE / f"data/inputs/{original}.json",
                 "sql": BASELINE / f"data/gold/{original}/label.json",
                 "answers": BASELINE / f"data/gold/{original}/answer.json"}
        for path in paths.values():
            files[str(path.relative_to(WORKSPACE))] = sha(path)
        inputs = load(paths["inputs"])["data"]
        sqls, answers = load(paths["sql"]), load(paths["answers"])
        ids = [r["id"] for r in inputs]
        if len(set(ids)) != len(ids) or set(ids) != set(sqls) or set(ids) != set(answers):
            raise ValueError("Source IDs incomplete or duplicated: " + split)
        references, clean_inputs, verbalizer_inputs = [], [], []
        summary = {"n": len(ids), "answerable": 0, "unanswerable": 0, "empty_results": 0,
                   "full_results_over_100_rows": 0, "max_result_rows": 0,
                   "SQL_missing_value_cells": 0, "official_gold_matches": 0, "text_roundtrip_matches": 0}
        for entry in inputs:
            key = entry["id"]
            sql, official = sqls[key], answers[key]
            answerable = sql != "null"
            if answerable != (official != "null"):
                raise ValueError("Gold answerability mismatch: " + key)
            processed, raw_rows, rows = None, None, None
            if answerable:
                processed = core.post_process_sql(sql)
                if processed not in cache:
                    try:
                        cache[processed] = core.execute_readonly(processed, DATABASE, timeout_s)
                    except Exception as error:
                        raise RuntimeError(f"Cannot label {split}/{key}; no label was invented") from error
                raw_rows = cache[processed]
                if core.process_answer(raw_rows) != core.process_answer(official):
                    raise ValueError("Gold execution mismatch; no silent repair: " + key)
                rows = canonical_rows(raw_rows)
                summary["max_result_rows"] = max(summary["max_result_rows"], len(rows))
                summary["full_results_over_100_rows"] += len(rows) > 100
                summary["empty_results"] += not rows
                summary["SQL_missing_value_cells"] += sum(c is None for row in rows for c in row)
            summary["answerable" if answerable else "unanswerable"] += 1
            summary["official_gold_matches"] += 1
            output = render_answer(rows, answerable=answerable)
            decoded = parse_controlled_answer(output)
            if decoded != {"answerable": answerable, "rows": rows}:
                raise ValueError("Text facts changed: " + key)
            summary["text_roundtrip_matches"] += 1
            refs = {"id": key, "split": split, "source_split": original,
                    "input_text": entry["question"], "input_sql": sql,
                    "executable_gold_sql": processed, "official_gold_answer": official,
                    "answerable": answerable, "result_rows": rows,
                    "output_text": output, "annotation_method": RENDERER_VERSION,
                    "annotation_status": "automatic_reference_not_human_validated",
                    "full_result_rows": len(rows) if rows is not None else None,
                    "official_gold_uses_100_row_cap": bool(rows is not None and len(rows) > 100)}
            references.append(refs)
            clean_inputs.append({"id": key, "input_text": entry["question"]})
            # Gold SQL/results are legitimate inputs ONLY when isolating the
            # verbalizer. They must not be used for question-only end-to-end QA.
            verbalizer_inputs.append({"id": key, "input_text": entry["question"],
                                      "input_sql": sql, "executable_sql": processed,
                                      "result_rows": rows, "answerable": answerable})
        ref_path = destination / "references" / f"{split}.jsonl"
        input_path = destination / "inputs" / f"{split}.jsonl"
        write_jsonl(ref_path, references)
        write_jsonl(input_path, clean_inputs)
        verbalizer_path = destination / "sql_to_text_inputs" / f"{split}.jsonl"
        write_jsonl(verbalizer_path, verbalizer_inputs)
        csv_path = destination / "references" / f"{split}.csv"
        with csv_path.open("w", encoding="utf-8-sig", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=list(references[0]))
            writer.writeheader()
            for record in references:
                writer.writerow({k: json.dumps(v, ensure_ascii=False) if isinstance(v, (list, dict)) else v
                                 for k, v in record.items()})
        summary.update(reference_sha256=sha(ref_path), input_sha256=sha(input_path),
                       sql_to_text_input_sha256=sha(verbalizer_path), csv_sha256=sha(csv_path))
        manifest["splits"][split] = summary
        print(split, summary, flush=True)
    # Verify every source after the entire build, including the database.
    for name, digest in files.items():
        if sha(WORKSPACE / name) != digest:
            raise ValueError("Original changed during annotation: " + name)
    manifest["source_sha256"] = files
    manifest["implementation_sha256"] = {p.name: sha(p) for p in (HERE / "build_references.py", HERE / "reference_renderer.py", HERE / "common_io.py")}
    verify_frozen()
    dump(destination / "MANIFEST.json", manifest)
    return manifest


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=HERE / "data")
    parser.add_argument("--sql-timeout", type=float, default=120, help="Read-only timeout per gold SQL; not a scoring/runtime benchmark")
    args = parser.parse_args()
    build(args.output, args.sql_timeout)
