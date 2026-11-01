"""Second, independent audit of all English-answer reference files.

Does not import the renderer, builder, or previous audit implementations.
Only read-only execution of gold SQL; no models, credentials or network.
"""
from __future__ import annotations

import ast
from collections import Counter
import csv
import hashlib
import importlib.util
import json
import math
from pathlib import Path
import re
import sqlite3
import time

OUT = Path(__file__).resolve().parent
PACKAGE = OUT.parents[1]
WORKSPACE = PACKAGE.parents[1]
BASELINE = WORKSPACE / "baselines/probgate_ehrsql_2024"
DB = BASELINE / "upstream/src/data/mimic_iv/mimic_iv.sqlite"


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def lines(path):
    return [json.loads(x) for x in Path(path).read_text(encoding="utf-8-sig").splitlines() if x.strip()]


def digest(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for part in iter(lambda: stream.read(2**20), b""):
            h.update(part)
    return h.hexdigest()


def number_or_string(v):
    if v is None:
        return None
    try:
        f = float(v)
    except (ValueError, TypeError):
        return str(v)
    if not math.isfinite(f):
        raise ValueError("nonfinite numeric value")
    return str(round(f, 3))


def normalize(rows):
    cells = [[number_or_string(v) for v in row] for row in rows]
    return sorted(cells, key=lambda row: tuple(("None" if v is None else v, v is not None) for v in row))


def official_normalize(rows):
    # Official treats None as string and caps sorted rows at100. Current gold
    # SQL contains no None, but keep that distinction explicit here.
    return sorted([["None" if v is None else number_or_string(v) for v in row] for row in rows])[:100]


def extract_text(text):
    if text == "This question cannot be answered using the available database.":
        return False, None
    if text == "The query returned no rows.":
        return True, []
    scalar = re.fullmatch(r"The returned value is (.+)\.", text)
    if scalar:
        value = json.loads(scalar[1])
        if value is not None and not isinstance(value, str):
            raise ValueError("non-string scalar")
        expected = "The returned value is " + json.dumps(value, ensure_ascii=False) + "."
        if expected != text:
            raise ValueError("noncanonical scalar text")
        return True, [[value]]
    portions = text.split("\n")
    header = re.fullmatch(r"The query returned ([1-9][0-9]*) rows\.", portions[0])
    if not header or len(portions) != int(header[1]) + 1:
        raise ValueError("invalid text header/row count")
    rows = []
    for i, sentence in enumerate(portions[1:], 1):
        prefix = f"Row {i}: "
        if not sentence.startswith(prefix) or not sentence.endswith("."):
            raise ValueError("invalid row statement")
        row = json.loads(sentence[len(prefix):-1])
        if not isinstance(row, list) or not row or any(v is not None and not isinstance(v, str) for v in row):
            raise ValueError("invalid cells")
        if prefix + json.dumps(row, ensure_ascii=False) + "." != sentence:
            raise ValueError("trailing or unparsed prose")
        rows.append(row)
    return True, rows


def main():
    started = time.monotonic()
    manifest = read(PACKAGE / "data/MANIFEST.json")
    lock = read(WORKSPACE / "experiments/research_validation/V5_LOCK.json")
    watched = {str(WORKSPACE / name): value for name, value in lock["files"].items()}
    watched.update({str(WORKSPACE / name): value for name, value in manifest["source_sha256"].items()})
    for name, expected in watched.items():
        assert digest(name) == expected, "initial source/frozen hash: " + name
    spec = importlib.util.spec_from_file_location("author_postprocess_independent_final", BASELINE / "upstream/src/scoring_program/postprocessing.py")
    pp = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(pp)
    conn = sqlite3.connect(DB.resolve().as_uri() + "?mode=ro", uri=True)
    conn.execute("PRAGMA query_only=ON")
    totals, groups, errors, examples, all_ids = Counter(), {}, [], {}, set()
    normalized_question_sets = {}
    try:
        for split, original in (("train", "train"), ("validation", "dev"), ("test", "test")):
            counts = Counter()
            source = read(BASELINE / f"data/inputs/{original}.json")["data"]
            gold_sql = read(BASELINE / f"data/gold/{original}/label.json")
            gold_answer = read(BASELINE / f"data/gold/{original}/answer.json")
            refs = lines(PACKAGE / f"data/references/{split}.jsonl")
            clean = lines(PACKAGE / f"data/inputs/{split}.jsonl")
            component = lines(PACKAGE / f"data/sql_to_text_inputs/{split}.jsonl")
            with (PACKAGE / f"data/references/{split}.csv").open(encoding="utf-8-sig", newline="") as stream:
                csv_rows = list(csv.DictReader(stream))
            source_ids = [x["id"] for x in source]
            assert len(source_ids) == len(set(source_ids))
            assert not set(source_ids) & all_ids, "IDs overlap across splits"
            all_ids.update(source_ids)
            assert source_ids == [x["id"] for x in refs] == [x["id"] for x in csv_rows]
            assert set(source_ids) == set(gold_sql) == set(gold_answer)
            assert clean == [{"id": q["id"], "input_text": q["question"]} for q in source]
            assert len(component) == len(refs)
            normalized_question_sets[split] = {re.sub(r"\W+", " ", x["question"].casefold()).strip() for x in source}
            for q, r, csv_row, verbalizer in zip(source, refs, csv_rows, component):
                key = q["id"]
                counts["questions"] += 1
                try:
                    assert r["input_text"] == q["question"] and r["input_sql"] == gold_sql[key]
                    assert r["official_gold_answer"] == gold_answer[key]
                    assert r["split"] == split and r["source_split"] == original
                    assert r["annotation_status"] == "automatic_reference_not_human_validated"
                    assert csv_row == {k: json.dumps(v, ensure_ascii=False) if isinstance(v, (dict, list)) else "" if v is None else str(v) for k, v in r.items()}
                    assert verbalizer == {"id": key, "input_text": q["question"], "input_sql": gold_sql[key],
                                         "executable_sql": r["executable_gold_sql"], "result_rows": r["result_rows"], "answerable": r["answerable"]}
                    answerable = gold_sql[key] != "null"
                    assert answerable == (gold_answer[key] != "null") == r["answerable"]
                    if answerable:
                        processed = pp.post_process_sql(gold_sql[key])
                        assert r["executable_gold_sql"] == processed
                        deadline = time.monotonic() + 120
                        conn.set_progress_handler(lambda: int(time.monotonic() > deadline), 10000)
                        raw = conn.execute(processed).fetchall()
                        expected = normalize(raw)
                        assert official_normalize(raw) == official_normalize(ast.literal_eval(gold_answer[key]))
                        assert r["full_result_rows"] == len(raw)
                        assert r["official_gold_uses_100_row_cap"] is (len(raw) > 100)
                        counts["executed_SQL"] += 1
                        counts["official_gold_equivalent"] += 1
                        counts["full_result_over_100_rows"] += len(raw) > 100
                        counts["queries_with_duplicate_rows"] += len(raw) != len(set(raw))
                        counts["SQL_NULL_cells"] += sum(v is None for row in raw for v in row)
                        counts["empty_results"] += not raw
                        counts["multi_column_queries"] += bool(raw and len(raw[0]) > 1)
                        counts["max_full_result_rows"] = max(counts["max_full_result_rows"], len(raw))
                        if re.match(r"(?i)^(is|are|was|were|does|do|did|has|have|had|can)\b", q["question"]):
                            counts["yes_no_wording_answerable"] += 1
                            if "yes_no" not in examples:
                                examples["yes_no"] = {"split": split, "id": key, "question": q["question"], "output_text": r["output_text"], "raw_result": raw}
                        if re.search(r"\btop\b|\bmost common\b|\bfrequent", q["question"], re.I) and len(raw) > 100 and "top_k_over_100" not in examples:
                            examples["top_k_over_100"] = {"split": split, "id": key, "question": q["question"], "SQL_rank_rule": "DENSE_RANK" if "DENSE_RANK" in processed.upper() else "other", "full_rows": len(raw), "official_rows": len(ast.literal_eval(gold_answer[key]))}
                        if re.match(r"(?is)^\s*SELECT\s+(?:DISTINCT\s+)?(?:[A-Za-z0-9_]+\.)?subject_id\s+FROM\b", processed) and raw and "numeric_patient_ID" not in examples:
                            examples["numeric_patient_ID"] = {"split": split, "id": key, "question": q["question"], "raw_result": raw, "output_text": r["output_text"]}
                    else:
                        expected = None
                        assert r["full_result_rows"] is None and r["executable_gold_sql"] is None
                        counts["unanswerable"] += 1
                    parsed_answerable, parsed_rows = extract_text(r["output_text"])
                    assert parsed_answerable == answerable and parsed_rows == expected == r["result_rows"]
                    counts["independently_parsed_facts_match"] += 1
                    counts["CSV_and_inputs_match"] += 1
                except Exception as exc:
                    errors.append({"split": split, "id": key, "error": type(exc).__name__ + ": " + str(exc)})
            groups[split] = dict(counts)
            for k, v in counts.items():
                if k == "max_full_result_rows":
                    totals[k] = max(totals[k], v)
                else:
                    totals[k] += v
            for subfolder, ext, field in (("references", "jsonl", "reference_sha256"), ("references", "csv", "csv_sha256"),
                                          ("inputs", "jsonl", "input_sha256"), ("sql_to_text_inputs", "jsonl", "sql_to_text_input_sha256")):
                assert digest(PACKAGE / f"data/{subfolder}/{split}.{ext}") == manifest["splits"][split][field]
    finally:
        conn.close()
    for name, expected in watched.items():
        assert digest(name) == expected, "source changed during audit: " + name
    overlaps = {a + "_" + b: len(normalized_question_sets[a] & normalized_question_sets[b])
                for a, b in (("train", "validation"), ("train", "test"), ("validation", "test"))}
    report = {"date": "2026-11-01", "status": "passed_with_scope_limitations" if not errors else "failed",
              "audit_kind": "Second independent full-corpus SQL execution and text facts audit",
              "imported_previous_builder_or_renderer_or_audit": False, "new_API_calls": 0,
              "counts": dict(totals), "splits": groups, "cross_split_ID_overlap": 0,
              "normalized_question_text_overlap": overlaps, "examples": examples,
              "frozen_files_verified": len(lock["files"]), "original_artifacts_unchanged": True,
              "reference_manifest_sha256": digest(PACKAGE / "data/MANIFEST.json"),
              "errors": errors, "error_count": len(errors),
              "findings": [
                  {"severity": "scope", "title": "Controlled value rendering, not conversational or clinical validation",
                   "details": "The labels faithfully state query values and lists. They do not independently explain the question, infer units, decode numeric IDs, convert 0/1 to Yes/No, or verify the clinical meaning of gold SQL. Thus they are a generated silver extension, not a clinician-validated English QA benchmark."},
                  {"severity": "scope", "title": "Full-result English references intentionally differ from official cap100",
                   "details": "44 queries have more than100 result rows; full English outputs preserve up to152 rows. Do not compare English factEM numerically with published SQL execution scores as if the tasks/normalizers were identical."}],
              "elapsed_seconds": round(time.monotonic() - started, 3)}
    (OUT / "annotation_audit.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    text = ["# Audit độc lập vòng hai — nhãn tiếng Anh", "", f"Ngày 01/11/2026. Trạng thái: {report['status']}. Không API/model call.", "",
            f"Đã kiểm tra đủ {totals['questions']} câu, thực thi lại {totals['executed_SQL']} SQL chuẩn read-only; {totals['independently_parsed_facts_match']} câu tiếng Anh khớp dữ kiện kết quả theo numeric3/toàn bộ dòng. Lỗi phát hiện: {len(errors)}.", "",
            "Không import builder, renderer hoặc các audit cũ. Kiểm tra độc lập SQL/result, grammar của text, CSV, input chỉ có câu hỏi, input riêng cho verbalizer, ID/split và hash nguồn/147 file đóng băng.", "",
            "- train:5.124; validation:1.163; test:1.167. Không trùng ID giữa các split.",
            f"- Câu không thể trả lời:{totals['unanswerable']}; kết quả rỗng:{totals['empty_results']}; SQL NULL:{totals['SQL_NULL_cells']}.",
            f"- Query có dòng trùng:{totals['queries_with_duplicate_rows']}; query trên100dòng:{totals['full_result_over_100_rows']}; tối đa:{totals['max_full_result_rows']}dòng.", "",
            "## Giới hạn phải giữ trong kết luận", "",
            "Các nhãn là tiếng Anh có kiểm soát chỉ nêu giá trị, chưa phải câu trả lời hội thoại được bác sĩ duyệt. Câu hỏi Yes/No có thể nhận giá trị0.0/1.0, mã bệnh nhân có thể được numeric3 chuyển thành số có đuôi.0. Điều này giữ quy ước chấm, nhưng chưa kiểm định độ tự nhiên hoặc ý nghĩa lâm sàng. Audit máy không chứng minh nhãn hoàn toàn chính xác về mặt ngữ nghĩa.", "",
            "Full-result English giữ152dòng trong ví dụ top-k có DENSE_RANK đồng hạng, trong khi gold official chỉ100dòng. Đây là khác biệt phạm vi đã khai báo, không phải lỗi cần tự cắt dữ liệu.", "",
            "Ví dụ và toàn bộ số liệu/hash nằm trong annotation_audit.json. Không sửa bất kỳ artifact gốc nào."]
    (OUT / "annotation_audit.md").write_text("\n".join(text) + "\n", encoding="utf-8")
    print(json.dumps({k: report[k] for k in ("status", "counts", "error_count", "normalized_question_text_overlap", "elapsed_seconds")}, ensure_ascii=False))


if __name__ == "__main__":
    main()
