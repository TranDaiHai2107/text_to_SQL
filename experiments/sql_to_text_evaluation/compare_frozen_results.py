"""Fresh offline comparison of the four frozen English-to-SQL predictions.

No model clients, key access, generation, training, or mutation of legacy data.
Run from any working directory: python <this-file>.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sqlite3
import sys
import time

ROOT = Path(__file__).resolve().parent
WORKSPACE = ROOT.parents[1]
BASELINE = WORKSPACE / "baselines/probgate_ehrsql_2024"
EXPERIMENTS = WORKSPACE / "experiments"
sys.path.insert(1, str(BASELINE))
from baseline_core import execute_readonly, score_answers


def load(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def sha(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main():
    started = time.monotonic()
    lock_path = EXPERIMENTS / "research_validation/V5_LOCK.json"
    lock = load(lock_path)
    for relative, digest in lock["files"].items():
        if sha(WORKSPACE / relative) != digest:
            raise ValueError("Frozen file changed: " + relative)
    confirmed_path = EXPERIMENTS / "result_confirmation/CONFIRMED_RESULTS.json"
    confirmed = load(confirmed_path)
    manifest = load(BASELINE / "source_manifest.json")
    database = BASELINE / manifest["database_path"]
    inputs = load(BASELINE / "data/inputs/test.json")["data"]
    gold = load(BASELINE / "data/gold/test/answer.json")
    labels = load(BASELINE / "data/gold/test/label.json")
    expected = {item["id"] for item in inputs}
    answerable = {key for key, value in gold.items() if value != "null"}
    if (len(inputs) != 1167 or len(expected) != 1167 or set(gold) != expected
            or set(labels) != expected or len(answerable) != 934
            or {key for key, value in labels.items() if value != "null"} != answerable):
        raise ValueError("Original complete 1167-question test required")

    sources = {
        "V5": (EXPERIMENTS / "ours_improved_v5/runs/deepseek_flash_v5_20261029_r1/test/v5_selected.prediction.json",
               load(EXPERIMENTS / "ours_improved_v5/runs/deepseek_flash_v5_20261029_r1/test/evaluation.json")["variants"]["v5_selected"]),
        "Vanna": (EXPERIMENTS / "vanna_ehrsql/runs/deepseek_flash_train_dev_20261028_v1/vanna.prediction.json",
                  load(EXPERIMENTS / "vanna_ehrsql/runs/deepseek_flash_train_dev_20261028_v1/evaluation.json")["variants"]["vanna"]),
        "Vanna_GEF": (EXPERIMENTS / "vanna_ehrsql/runs/deepseek_flash_train_dev_20261028_v1/vanna_gef.prediction.json",
                      load(EXPERIMENTS / "vanna_ehrsql/runs/deepseek_flash_train_dev_20261028_v1/evaluation.json")["variants"]["vanna_gef"]),
        "ProbGate_paper_cache": (BASELINE / "runs/audit_20261023_docker/test_gpt_probgate_425_gef/prediction.json",
                                load(BASELINE / "runs/audit_20261023_docker/test_gpt_probgate_425_gef/scores_official.json")),
    }
    answer_cache = {}
    systems = {}
    for name, (path, historical) in sources.items():
        predictions = load(path)
        if set(predictions) != expected or not all(isinstance(sql, str) for sql in predictions.values()):
            raise ValueError("Missing, extra, or invalid prediction: " + name)
        answers = {}
        errors = 0
        for key, sql in predictions.items():
            if sql == "null":
                answers[key] = "null"
            elif not sql.strip():
                # SQLite.execute('') returns [], but this exported invalid SQL
                # is an execution failure, never a correct abstention.
                answers[key] = "error_pred"
                errors += 1
            else:
                if sql not in answer_cache:
                    try:
                        answer_cache[sql] = execute_readonly(sql, database, 30)
                    except (sqlite3.Error, TypeError, ValueError):
                        answer_cache[sql] = "error_pred"
                answers[key] = answer_cache[sql]
                errors += answers[key] == "error_pred"
        result = score_answers(gold, answers, "official")
        if result["per_question"] != historical["per_question"] or result["scores"] != historical["scores"]:
            raise ValueError("Fresh per-question score differs: " + name)
        answered = sum(sql != "null" for sql in predictions.values())
        correct_sql = sum(result["per_question"][key] == "correct" for key in answerable)
        entry = {key: value for key, value in result.items() if key != "per_question"}
        entry.update(
            EX=100 * correct_sql / len(answerable),
            VSR=100 * (answered - errors) / len(inputs),
            coverage=100 * answered / len(inputs),
            answer_precision=100 * correct_sql / answered,
            correct_answerable_sql=correct_sql,
            correct_abstentions=result["correct"] - correct_sql,
            false_answers_on_unanswerable=sum(result["per_question"][key] == "wrong" for key in expected - answerable),
            execution_errors=errors,
            matches_historical_per_question=True,
            prediction_source=path.relative_to(WORKSPACE).as_posix(),
            prediction_sha256=sha(path),
            model="deepseek-flash" if name != "ProbGate_paper_cache" else "author-released fine-tuned GPT predictions; model not rerun",
        )
        prior = confirmed["systems"][name]
        for key in ("correct", "wrong", "abstained_answerable", "scores", "EX", "VSR"):
            if entry[key] != prior[key]:
                raise ValueError(f"Original confirmation differs: {name}.{key}")
        if name == "ProbGate_paper_cache":
            published = {"RS0": 81.92, "RS5": 78.06, "RS10": 74.21, "RSN": -818.08}
            if any(round(result["scores"][key], 2) != value for key, value in published.items()):
                raise ValueError("Paper published rounded scores differ")
            entry.update(published_RS=published, EX_and_VSR_source="computed here from released predictions; not published paper columns")
        systems[name] = entry
        print(name, "RS10", round(entry["scores"]["RS10"], 6), "EX", round(entry["EX"], 6), flush=True)

    report = {
        "date": "2026-11-01",
        "timezone": "Asia/Bangkok",
        "state": "fresh_read_only_execution_matches_all_frozen_per_question_scores",
        "scope": "English-to-SQL only; no new English-answer scores attributed to the paper",
        "questions": 1167, "answerable": 934, "unanswerable": 233,
        "new_model_API_calls": 0,
        "frozen_source_files_verified": len(lock["files"]),
        "source_confirmation_sha256": sha(confirmed_path),
        "database_sha256": sha(database),
        "scorer_sha256": sha(BASELINE / "baseline_core.py"),
        "runtime": {"execution": "read-only host SQLite", "sqlite": sqlite3.sqlite_version, "fresh_Docker_execution": False},
        "systems": systems,
        "metric_definitions": {
            "RS_c": "100 * (correct - c * wrong) / N; correct includes correct SQL and correct unanswerable refusal; false refusal scores zero",
            "RSN": "c=N=1167",
            "EX": "100 * execution-correct SQL / 934 answerable questions (errors and false refusals retained)",
            "VSR": "100 * successfully executed SQL / all 1167 questions; abstentions not executable SQL",
            "coverage": "100 * non-null SQL predictions / 1167; invalid SQL still counts as attempted",
            "answer_precision": "100 * execution-correct SQL / all non-null attempts",
        },
        "v5_minus_paper_RS10": systems["V5"]["scores"]["RS10"] - systems["ProbGate_paper_cache"]["scores"]["RS10"],
        "research_superiority_proven": False,
        "research_note": "V5 was finalized after repeated test observations; models, fine-tuning, knowledge and inference budgets differ. This confirms measured numbers, not causal method superiority or independent generalization.",
        "paper_url": "https://aclanthology.org/2024.clinicalnlp-1.65/",
        "elapsed_seconds": time.monotonic() - started,
    }
    destination = ROOT / "results"
    destination.mkdir(parents=True, exist_ok=True)
    (destination / "TEXT_TO_SQL_COMPARISON.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    lines = [
        "# Kết quả cuối Text-to-SQL — đối chiếu ngày 01/11/2026", "",
        "Đã thực thi lại prediction đã lưu trên toàn bộ 1.167 câu test EHRSQL 2024 (934 answerable, 233 unanswerable). Từng kết quả chấm khớp kết quả cũ; 147 file đóng băng không đổi. Không gọi API, không chạy lại model, không sửa gold hoặc bộ chấm Text-to-SQL.", "",
    ]
    for name, item in systems.items():
        scores = item["scores"]
        lines += [
            f"- **{name}**: RS0 **{scores['RS0']:.2f}**, RS5 **{scores['RS5']:.2f}**, RS10 **{scores['RS10']:.2f}**, RSN **{scores['RSN']:.2f}**; EX **{item['EX']:.2f}%**, VSR **{item['VSR']:.2f}%**.",
            f"  Đúng SQL: {item['correct_answerable_sql']}; từ chối đúng: {item['correct_abstentions']}; trả lời sai: {item['wrong']}; từ chối nhầm câu có đáp án: {item['abstained_answerable']}; lỗi thực thi: {item['execution_errors']}. Precision trên các câu đã trả lời: {item['answer_precision']:.2f}%.",
        ]
    lines += [
        "", "## Đọc các chỉ số", "",
        "- RS(c) = 100 × (số đúng − c × số trả lời sai) / 1.167. Số đúng gồm SQL đúng và từ chối đúng; từ chối nhầm nhận 0. RSN dùng c=1.167.",
        "- EX chỉ có mẫu số 934 câu có đáp án. VSR có mẫu số toàn bộ 1.167 câu và đo khả năng thực thi SQL, không đo nội dung đúng.",
        "- Vanna_GEF là cùng lần sinh của Vanna có thêm bộ lọc thực thi/kết quả rỗng; không phải lần chạy một model khác.",
        "", "## Nguồn và giới hạn so sánh", "",
        "[ProbGate at EHRSQL 2024: Enhancing SQL Query Generation Accuracy through Probabilistic Threshold Filtering and Error Handling](https://aclanthology.org/2024.clinicalnlp-1.65/) công bố các điểm RS. EX và VSR ở đây được tính thêm từ prediction tác giả phát hành, không phải hai cột công bố trong bài báo. Đây là replay prediction tác giả, chưa tái huấn luyện/chạy lại model tác giả.", "",
        "V5 và Vanna đều dùng DeepSeek Flash, nhưng V5 có ba nhánh sinh/chọn SQL nên ngân sách inference chưa bằng nhau. Bài báo dùng model và quy trình fine-tune khác. V5 dùng train+dev làm knowledge; test đã được quan sát trong quá trình phát triển nhiều phiên bản.", "",
        f"V5 nhỉnh hơn paper **{report['v5_minus_paper_RS10']:.4f} điểm RS10 quan sát**, và hơn Vanna trong cấu hình đã chạy. Paper vẫn ít câu sai hơn (9 so với 21) và RSN tốt hơn. Chênh lệch này **chưa chứng minh ưu thế nghiên cứu độc lập**; khoảng tin cậy paired-bootstrap đã lưu của RS10 [-9,08; 10,20] chứa 0.", "",
        "Kết quả này chỉ đánh giá English→SQL. Phần tham chiếu và metric English→English mới phải được báo cáo riêng; không gán điểm SQL→text cho paper khi paper không công bố phần đó.", "",
        "Chi tiết nguồn, hash, mẫu số và công thức nằm trong `TEXT_TO_SQL_COMPARISON.json`. Lần kiểm tra này chạy SQLite trên host, không gắn nhãn fresh Docker verification.", "",
    ]
    (destination / "TEXT_TO_SQL_COMPARISON_VI.md").write_text("\n".join(lines), encoding="utf-8")
    return report


if __name__ == "__main__":
    main()
