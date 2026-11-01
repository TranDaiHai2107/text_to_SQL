"""Assemble the three independent audits without querying a model or database."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
PACKAGE = HERE.parents[1]


def load(path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    comparison = load(HERE / "comparison_audit.json")
    annotation = load(HERE / "annotation_audit.json")
    metrics = load(HERE / "metric_audit.json")
    delivery = load(PACKAGE / "results/DELIVERY_VALIDATION.json")
    latest = metrics["runs"][-1]
    assert comparison["audit_status"] == "passed"
    assert annotation["status"] == "passed_with_scope_limitations" and annotation["error_count"] == 0
    assert not latest["findings"] and all(case["passed"] for case in latest["checks"])
    assert latest["code_sha256"]["english_metrics.py"] == sha(PACKAGE / "english_metrics.py")
    assert delivery["artifact_sha256"]["english_metrics.py"] == sha(PACKAGE / "english_metrics.py")
    assert delivery["status"] == "passed" and delivery["unit_tests"]["failures"] == delivery["unit_tests"]["errors"] == 0
    report = {
        "date": "2026-11-01", "status": "passed_after_two_input_integrity_fixes_with_declared_scope_limits",
        "independent_agents": 3, "new_model_API_calls": 0, "original_frozen_files_unchanged": 147,
        "comparison": {"systems": 4, "questions_per_system": 1167,
                       "all_historical_per_question_outcomes_match": True,
                       "RS10": {k: v["scores"]["RS10"] for k, v in comparison["systems"].items()}},
        "annotations": {"questions": 7454, "fresh_gold_SQL_executed": 6539, "errors": 0,
                        "references_changed_by_this_audit": False,
                        "human_or_clinician_validated": False},
        "fixed_findings": [
            {"severity": "P2", "finding": "Duplicate JSON mapping IDs/fields could silently overwrite prior values",
             "fix": "Reject duplicate object keys during JSON/JSONL decoding", "status": "independently_retested_fixed"},
            {"severity": "P2", "finding": "Controlled reference text could contradict its structured result_rows",
             "fix": "Parse gold English and require agreement with answerable/result_rows before grading predictions",
             "status": "independently_retested_fixed"}
        ],
        "regression_validation": {"pytest_test_functions": 61, "successful_subtests": 5,
                                  "JUnit_cases": delivery["unit_tests"]["tests"],
                                  "independent_metric_checks": len(latest["checks"]),
                                  "independent_DP_sequence_pairs": 961,
                                  "full_corpus_scorer_self_check": "passed_NOT_model_performance"},
        "unresolved_scope_limits": [
            "Generated controlled-English references preserve executed gold results, not clinician-approved conversational answers",
            "Strict fact parser requires canonical spelling/order; arbitrary English paraphrases need a separate semantic validator",
            "Full-result English keeps rows beyond100; published SQL scorer caps100, so scores are not interchangeable",
            "No actual SQL-to-text model generation evaluation has been performed",
            "V5 test-informed development and unequal models/budgets prevent claiming independent research superiority"
        ],
        "evidence_sha256": {path.name: sha(path) for path in [HERE / "comparison_audit.json", HERE / "annotation_audit.json",
                            HERE / "metric_audit.json", PACKAGE / "results/DELIVERY_VALIDATION.json"]}
    }
    (HERE / "AUDIT_SUMMARY.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    text = """# Tổng hợp audit độc lập — 01/11/2026

Ba agent kiểm tra riêng số liệu Text-to-SQL, toàn bộ nhãn tiếng Anh và bộ chấm. Không gọi API hoặc model; 147 file đã chốt giữ nguyên.

## Kết quả xác nhận

- So sánh: replay độc lập 4 × 1.167 prediction, khớp từng kết quả chấm cũ; RS/EX/VSR, các số đếm và mẫu số không sai. RS10 vẫn là V5: 74,89; Vanna: −58,10; Vanna+GEF: −12,08; ProbGate: 74,21.
- Nhãn: thực thi lại 6.539 SQL chuẩn; 7.454/7.454 output tiếng Anh khớp toàn bộ dữ kiện theo numeric3; 0 lỗi, 0 timeout. CSV/JSONL, membership các split, input sạch và input verbalizer đều đúng. Không đổi nhãn.
- Bộ chấm: 27 kiểm tra audit độc lập đạt, gồm đối chiếu DP trên 961 cặp chuỗi. Sau sửa có 61 test và 5 subtest đạt (66 case theo JUnit); self-check scorer toàn bộ ba split đạt, không phải điểm mô hình.

## Hai lỗi đã tìm và sửa

1. **P2 — JSON trùng ID/key bị ghi đè âm thầm.** Loader mới từ chối key trùng trong cả JSON và JSONL trước khi mất bản ghi ban đầu. Có test hồi quy và agent kiểm tra lại.
2. **P2 — reference text có thể mâu thuẫn result_rows.** Chế độ controlled giờ parse gold English và yêu cầu khớp dữ kiện/trạng thái trước khi chấm prediction. Reference mâu thuẫn dừng chấm. Có test hồi quy và agent kiểm tra lại.

Hai lỗi nằm ở việc tiếp nhận đầu vào mới của scorer. Nhãn hiện tại không có các mâu thuẫn này; kết quả Text-to-SQL đã báo cáo không bị ảnh hưởng. Các lỗi trước sửa được ghi nhận bằng probe tương tác; các lần chạy script audit lưu trong metric_audit.json đều diễn ra sau sửa. Không gắn nhãn nhầm các script sau sửa là bằng chứng thực thi trước sửa.

## Giới hạn vẫn phải giữ

- Nhãn mới là tiếng Anh có kiểm soát nêu giá trị/kết quả SQL, chưa phải đáp án hội thoại được bác sĩ thẩm định. Câu hỏi Yes/No có thể nhận 0.0/1.0; không suy diễn thêm ý nghĩa lâm sàng.
- Fact-EM đòi đúng grammar canonical, cả cách viết số và sắp dòng; không tự xác nhận mọi paraphrase tiếng Anh.
- 44 câu giữ đủ hơn 100 dòng (tối đa 152), trong khi official SQL scorer giới hạn 100 dòng. Không so hai điểm như cùng tác vụ.
- Chưa đánh giá sinh tiếng Anh thực tế của V5/Vanna; chưa có kết quả SQL→text của paper để đối chiếu phần này.
- RS10 V5 nhỉnh hơn paper quan sát chưa chứng minh ưu thế nghiên cứu độc lập.

Chi tiết: [so sánh](comparison_audit.md), [nhãn](annotation_audit.md), [metric](metric_audit.md). Số liệu/hash máy đọc: AUDIT_SUMMARY.json.
"""
    (HERE / "AUDIT_SUMMARY_VI.md").write_text(text, encoding="utf-8")
    print(json.dumps({"status": report["status"], "fixed_findings": len(report["fixed_findings"]),
                      "agents": 3, "labels_checked": 7454, "API_calls": 0}, ensure_ascii=False))


if __name__ == "__main__":
    main()
