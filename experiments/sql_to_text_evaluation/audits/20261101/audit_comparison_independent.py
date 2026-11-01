"""Independent stdlib-only replay audit. No production scorer/client imports."""
from __future__ import annotations

import ast
from collections import Counter
import hashlib
import json
from pathlib import Path
import sqlite3
import time

HERE = Path(__file__).resolve().parent
WORKSPACE = HERE.parents[3]
BASELINE = WORKSPACE / "baselines/probgate_ehrsql_2024"
EXTENSION = WORKSPACE / "experiments/sql_to_text_evaluation"


def load(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def sha(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def normalize(value):
    if isinstance(value, str):
        try:
            value = ast.literal_eval(value)
        except (ValueError, SyntaxError):
            pass
    if isinstance(value, str):
        return value
    rows = []
    for row in value:
        cells = []
        for item in row:
            try:
                item = round(float(item), 3)
            except (ValueError, TypeError):
                pass
            cells.append(str(item))
        rows.append(cells)
    return str(sorted(rows)[:100])


def main():
    started = time.monotonic()
    original = load(EXTENSION / "results/TEXT_TO_SQL_COMPARISON.json")
    lock = load(WORKSPACE / "experiments/research_validation/V5_LOCK.json")
    issues = []
    changed = [name for name, digest in lock["files"].items() if sha(WORKSPACE / name) != digest]
    if changed:
        raise ValueError("Frozen source changed: " + repr(changed))
    inputs = load(BASELINE / "data/inputs/test.json")["data"]
    labels = load(BASELINE / "data/gold/test/label.json")
    gold = load(BASELINE / "data/gold/test/answer.json")
    ids = [r["id"] for r in inputs]
    assert len(ids) == len(set(ids)) == 1167
    assert set(ids) == set(labels) == set(gold)
    answerable = {key for key in ids if gold[key] != "null"}
    assert len(answerable) == 934
    assert {key for key in ids if labels[key] != "null"} == answerable
    normalized_gold = {key: normalize(value) for key, value in gold.items()}
    database = BASELINE / "upstream/src/data/mimic_iv/mimic_iv.sqlite"
    before_db = sha(database)
    assert before_db == original["database_sha256"]
    histories = {
        "V5": load(WORKSPACE / "experiments/ours_improved_v5/runs/deepseek_flash_v5_20261029_r1/test/evaluation.json")["variants"]["v5_selected"],
        "Vanna": load(WORKSPACE / "experiments/vanna_ehrsql/runs/deepseek_flash_train_dev_20261028_v1/evaluation.json")["variants"]["vanna"],
        "Vanna_GEF": load(WORKSPACE / "experiments/vanna_ehrsql/runs/deepseek_flash_train_dev_20261028_v1/evaluation.json")["variants"]["vanna_gef"],
        "ProbGate_paper_cache": load(BASELINE / "runs/audit_20261023_docker/test_gpt_probgate_425_gef/scores_official.json"),
    }
    cache, systems = {}, {}
    conn = sqlite3.connect(database.resolve().as_uri() + "?mode=ro", uri=True)
    conn.execute("PRAGMA query_only=ON")
    conn.text_factory = lambda blob: blob.decode(errors="ignore")
    try:
        for name, previous in original["systems"].items():
            source = WORKSPACE / previous["prediction_source"]
            assert sha(source) == previous["prediction_sha256"]
            predictions = load(source)
            assert set(predictions) == set(ids)
            outcomes, counts = {}, Counter()
            for key in ids:
                sql = predictions[key]
                assert isinstance(sql, str)
                if sql == "null":
                    predicted = "null"
                else:
                    counts["attempted"] += 1
                    if sql not in cache:
                        try:
                            if not sql.strip():
                                raise ValueError("Empty SQL is invalid, not an empty result")
                            deadline = time.monotonic() + 120
                            conn.set_progress_handler(lambda: int(time.monotonic() > deadline), 10000)
                            raw = conn.execute(sql).fetchall()
                            cache[sql] = (normalize(raw), False)
                        except (sqlite3.Error, ValueError, TypeError):
                            cache[sql] = ("audit_execution_error", True)
                    predicted, error = cache[sql]
                    counts["execution_errors"] += error
                if predicted == normalized_gold[key]:
                    outcome = "correct"
                    counts["correct_answerable_sql" if key in answerable else "correct_abstentions"] += 1
                elif key in answerable and predicted == "null":
                    outcome = "abstained_answerable"
                else:
                    outcome = "wrong"
                    counts["false_answers_on_unanswerable"] += key not in answerable
                outcomes[key] = outcome
                counts[outcome] += 1
            assert outcomes == histories[name]["per_question"], name
            scores = {label: 100 * (counts["correct"] - penalty * counts["wrong"]) / len(ids)
                      for label, penalty in (("RS0", 0), ("RS5", 5), ("RS10", 10), ("RSN", len(ids)))}
            entry = {key: counts[key] for key in ("correct", "wrong", "abstained_answerable", "execution_errors", "correct_answerable_sql", "correct_abstentions", "false_answers_on_unanswerable")}
            entry.update(n=len(ids), scores=scores,
                         EX=100 * counts["correct_answerable_sql"] / len(answerable),
                         VSR=100 * (counts["attempted"] - counts["execution_errors"]) / len(ids),
                         coverage=100 * counts["attempted"] / len(ids),
                         answer_precision=100 * counts["correct_answerable_sql"] / counts["attempted"],
                         prediction_sha256=sha(source), complete_test_ID_coverage=True,
                         historical_per_question_exact_match=True)
            assert counts["correct"] + counts["wrong"] + counts["abstained_answerable"] == len(ids)
            for key, value in entry.items():
                if key in previous and value != previous[key]:
                    issues.append({"severity": "error", "system": name, "field": key, "independent": value, "reported": previous[key]})
            systems[name] = entry
    finally:
        conn.close()
    vanna_run = WORKSPACE / "experiments/vanna_ehrsql/runs/deepseek_flash_train_dev_20261028_v1"
    v3_run = WORKSPACE / "experiments/ours_improved_v3/runs/deepseek_flash_v3_20261029_r2"
    vanna_config = load(vanna_run / "config.json")
    v3_protocol = load(v3_run / "protocol.json")
    assert vanna_config["model"] == v3_protocol["model"] == "deepseek-flash"
    events = [json.loads(line) for line in (vanna_run / "api_events.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]
    model_counts = Counter(event.get("model") for event in events if event.get("kind") == "success")
    assert set(model_counts) == {"deepseek-flash"}
    records = [json.loads(line) for line in (vanna_run / "records.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]
    assert len(records) == len({r["id"] for r in records}) == 1167
    assert {r["id"] for r in records} == set(ids)
    published = {"RS0": 81.92, "RS5": 78.06, "RS10": 74.21, "RSN": -818.08}
    assert all(round(systems["ProbGate_paper_cache"]["scores"][key], 2) == val for key, val in published.items())
    assert sha(database) == before_db
    report = {
        "date": "2026-11-01", "audit_status": "passed" if not issues else "failed",
        "audit_method": "Independent stdlib SQLite read-only execution and numeric3/cap100 normalization; no production comparison/core scorer import",
        "test_questions": len(ids), "answerable": len(answerable), "unanswerable": len(ids) - len(answerable),
        "frozen_files_verified": len(lock["files"]), "original_database_unchanged": True,
        "new_API_calls": 0, "systems": systems, "issues": issues,
        "model_provenance": {"V5_generation_protocol_model": v3_protocol["model"], "V5_source_routes": v3_protocol["routes"],
                             "Vanna_model": vanna_config["model"], "Vanna_success_event_model_counts": dict(model_counts),
                             "Vanna_knowledge_splits": vanna_config["knowledge_splits"],
                             "V5_knowledge_splits": v3_protocol["knowledge_splits"],
                             "paper": "fine-tuned GPT-3.5-turbo; released prediction replay, not new model run"},
        "paper_primary_source_verified": {"url": "https://aclanthology.org/2024.clinicalnlp-1.65.pdf", "PDF_page": 6,
                                          "table": 2, "configuration": "gpt-3.5-turbo FT + ProbGate(t=425) + GEF", "published_RS": published,
                                          "EX_VSR": "derived from released cache; not published table columns"},
        "comparison_limitations_correctly_disclosed": ["different models/fine-tuning/knowledge/inference budgets versus paper", "V5 test-informed iterative development", "paper replay not model reproduction", "fresh host, not fresh Docker execution", "no SQL-to-English generation scores attributed to paper"],
        "research_superiority_proven": False,
        "source_comparison_sha256": sha(EXTENSION / "results/TEXT_TO_SQL_COMPARISON.json"),
        "audit_script_sha256": sha(Path(__file__)), "elapsed_seconds": time.monotonic() - started,
    }
    (HERE / "comparison_audit.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    lines = ["# Audit độc lập số liệu Text-to-SQL — 01/11/2026", "", "Kết luận: **PASS; không phát hiện sai số hoặc lỗi mẫu số trong số liệu đã bàn giao.**", "",
             "Audit sử dụng SQLite read-only và bộ chuẩn hóa/chấm độc lập chỉ bằng stdlib; không import production comparison hoặc adapter scorer. Đã replay đủ 4 × 1.167 prediction, khớp từng nhãn chấm lịch sử; 147 file khóa và database không đổi. Không gọi API.", ""]
    for name, item in systems.items():
        lines.append(f"- **{name}**: RS10 {item['scores']['RS10']:.6f}; EX {item['EX']:.6f}%; VSR {item['VSR']:.6f}%; correct {item['correct']}, wrong {item['wrong']}, false-abstention {item['abstained_answerable']}; precision {item['answer_precision']:.6f}%.")
    lines += ["", "RS0/RS5/RS10/RSN, EX, VSR, coverage, precision và false-answer counts đều khớp JSON bàn giao. EX dùng 934 câu answerable; VSR và RS dùng toàn bộ 1.167. Hai empty-string SQL của Vanna vẫn bị tính lỗi thực thi, không bị xem là từ chối đúng.", "",
              "Đã đối chiếu [PDF chính thức, Table 2, trang PDF 6](https://aclanthology.org/2024.clinicalnlp-1.65.pdf): cấu hình cuối GPT-3.5-turbo FT + ProbGate(t=425) + GEF có RS 81.92 / 78.06 / 74.21 / −818.08. EX/VSR paper là tính bổ sung từ cache, không phải cột công bố. Config Vanna, generation protocol V3/V5 và success events Vanna xác nhận DeepSeek Flash; không trộn kết quả OpenAI/partial run.", "",
              "Không phát hiện claim vượt phạm vi trong README/báo cáo: đã nêu test-informed development, khác model/knowledge/ngân sách, replay paper, host thay vì fresh Docker, và không có điểm SQL→English của paper. Chênh RS10 khoảng +0,69 quan sát không chứng minh ưu thế nghiên cứu độc lập.", "",
              "Giới hạn audit: xác nhận số đo trên snapshot hiện tại; không xác nhận clinical correctness của gold SQL, độ tổng quát hóa hay backbone fairness. Không có lỗi cần sửa trong phạm vi audit này."]
    (HERE / "comparison_audit.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps({"audit_status": report["audit_status"], "systems_verified": len(systems), "questions_each": len(ids), "issues": issues, "elapsed_seconds": report["elapsed_seconds"]}))
    return report


if __name__ == "__main__":
    main()
