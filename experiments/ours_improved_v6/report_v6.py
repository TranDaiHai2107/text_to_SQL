"""Report the frozen SQL test and controlled-English evaluation, without inference."""
from __future__ import annotations

from collections import Counter
import json
from pathlib import Path

from run_v6 import DEFAULT_RUN, EXPERIMENTS, HERE, dump, frozen_check, load, read_rows, sha


def compact_sql(metric):
    return {key: value for key, value in metric.items() if key != "per_question"}


def report(run=DEFAULT_RUN):
    run = Path(run)
    sql = load(run / "test/evaluation.json")
    policy = load(run / "policy.json")
    lock = load(run / "TEST_LOCK.json")
    if sha(run / "policy.json") != lock["policy_sha256"]:
        raise ValueError("Selected policy changed")
    english = {name: load(run / "english" / name / "ENGLISH_EVALUATION.json")
               for name in ("V5_frozen", "V6_dev_selected", "oracle_renderer")}
    for name in ("V5_frozen", "V6_dev_selected"):
        if english[name]["prediction_source"]["sha256"] != sha(run / "test" / (name + ".prediction.json")):
            raise ValueError("English evaluated different SQL: " + name)
    if any(value["questions"] != 1167 or value["state"] != "complete" for value in english.values()):
        raise ValueError("Incomplete English evaluation")
    historical = load(EXPERIMENTS / "sql_to_text_evaluation/results/TEXT_TO_SQL_COMPARISON.json")
    improvements, changed_questions = Counter(), set()
    for row in read_rows(run / "test/records.jsonl"):
        for candidate in row["candidates"]:
            repair = candidate.get("v6_repair", {})
            if repair.get("proposal_accepted"):
                changed_questions.add(row["id"])
                improvements.update(change["kind"] for change in repair["changes"])
    old = load(run / "test/V5_frozen.prediction.json")
    new = load(run / "test/V6_dev_selected.prediction.json")
    # Paired question-level bootstrap is exploratory; it is NOT a confirmation
    # on a fresh holdout or a patient/template-cluster independence claim.
    import numpy as np
    outcomes = {"correct": 1, "wrong": -10, "abstained_answerable": 0}
    differences = np.array([outcomes[sql["systems"]["V6_dev_selected"]["per_question"][k]]
                            - outcomes[sql["systems"]["V5_frozen"]["per_question"][k]] for k in old], dtype=float)
    rng = np.random.default_rng(20261101)
    samples = [float(100 * np.mean(differences[rng.integers(0, len(old), len(old))])) for _ in range(10000)]
    interval = np.percentile(samples, [2.5, 97.5]).tolist()
    result = {
        "date": "2026-11-01", "status": "complete", "scope": "paper_EHRSQL2024_dataset_only",
        "primary_policy": policy["selected_policy"], "new_model_API_calls": 0,
        "source_model": "DeepSeek_Flash_unchanged_cached_V3_generation",
        "inherited_model_generation_cost_is_not_zero": True,
        "test_used_for_policy_selection": False, "test_has_historical_exposure": True,
        "SQL": {name: compact_sql(value) for name, value in sql["systems"].items()},
        "SQL_RS10_delta_vs_V5": sql["RS10_delta"],
        "SQL_RS10_delta_paired_question_bootstrap_95_exploratory": interval,
        "transitions_vs_V5": sql["transitions_vs_V5"],
        "candidate_repair_counts_by_kind": dict(improvements),
        "questions_with_accepted_candidate_repairs": len(changed_questions),
        "final_SQL_text_changed_questions": sum(old[k] != new[k] for k in old),
        "English": {name: {key: value[key] for key in ("task", "mode", "questions", "generator", "lexical", "controlled", "groups")}
                    for name, value in english.items()},
        "historical_SQL_references": {name: compact_sql(value) for name, value in historical["systems"].items()
                                      if name in ("Vanna", "Vanna_GEF", "ProbGate_paper_cache")},
        "original_frozen_files_verified": frozen_check(),
        "limitations": [
            "Incremental deterministic repair/selection replay; not a fresh model inference run or retrieval ablation",
            "Both development partitions were exposed; historical paper test was exposed before this work",
            "Only one policy selected from tune300 and frozen before this test; no test-driven retuning",
            "English answers are produced by a common deterministic controlled-language renderer, not an LLM",
            "English reference labels are a generated extension, not official paper English-answer gold or expert review",
            "English full-result fact EM does not share the paper SQL scorer's cap100; lexical similarity is not clinical correctness",
            "Oracle renderer is a functionality check with gold SQL, not system generation performance",
            "Paper comparison uses different model/budget; does not establish independent method superiority"
        ],
        "artifacts_sha256": {str(path.relative_to(run)): sha(path) for path in [run / "protocol.json", run / "policy.json",
            run / "TEST_LOCK.json", run / "TEST_COMPLETE.json", run / "test/evaluation.json",
            *[run / "english" / name / "ENGLISH_EVALUATION.json" for name in english]]},
    }
    dump(run / "FINAL_RESULTS.json", result)
    v5, v6 = result["SQL"]["V5_frozen"], result["SQL"]["V6_dev_selected"]
    lines = ["# V6 — kết quả phát triển và chạy lại trên dataset paper", "",
             "Ngày 01/11/2026. Chỉ EHRSQL 2024/MIMIC-IV snapshot của paper; không chuyển ngữ hoặc dataset khác.", "",
             "## Phương pháp và lựa chọn", "",
             "Tái sử dụng các ứng viên DeepSeek Flash đã sinh cho V5, bổ sung chuẩn hóa AST/output contract, literal ICD theo metadata và quy ước organism có bằng chứng train. Giữ nguyên model, generation, database, gold và official scorer. Incremental API call = 0; chi phí generation kế thừa không bằng 0.", "",
             "Research đối chiếu CHESS/DAIL-SQL về grounding/retrieval, PromptMind về đồng thuận thực thi, CHASE-SQL về candidate selection và nghiên cứu selective prediction. Đây là adaptation có giới hạn; không tái hiện nguyên các phương pháp đó, không fine-tune, không thêm GraphRAG hoặc verifier LLM chưa được đánh giá.", "",
             f"Grid 8 policy khai báo trước; chọn trên 300 tune: **{policy['selected_policy']}**. 100 câu development còn lại đã tiếp xúc khi phân tích rule, chỉ dùng mô tả; không gọi là audit độc lập. Khóa policy và hash code trước test. Chỉ chấm primary đã khóa và V5 đối chứng, không chọn lại sau khi xem test.", "",
             "Hai lỗi projection phát hiện trong code review (ORDER BY ordinal và yêu cầu cột kỳ rõ ràng) đã sửa trước test. Lượt dev trước review được đánh dấu obsolete, không dùng làm kết quả test.", "",
             "## Text-to-SQL — đủ 1.167 câu", ""]
    for name, metric in result["SQL"].items():
        scores = metric["scores"]
        lines.append(f"- **{name}**: RS0={scores['RS0']:.2f}; RS5={scores['RS5']:.2f}; RS10={scores['RS10']:.2f}; RSN={scores['RSN']:.2f}; EX={metric['EX']:.2f}%; VSR={metric['VSR']:.2f}%; precision={metric['answer_precision']:.2f}%. SQL đúng={metric['correct_answerable_sql']}; từ chối đúng={metric['correct_abstentions']}; sai={metric['wrong']}; từ chối nhầm={metric['abstained_answerable']}.")
    lines += ["", f"Chênh RS10 V6−V5: **{sql['RS10_delta']:+.4f} điểm**. Bootstrap ghép theo câu hỏi 95% [{interval[0]:.2f}; {interval[1]:.2f}], chỉ mang tính exploratory, không xác nhận trên holdout mới.",
              "", "Chuyển trạng thái từng câu: " + json.dumps(sql["transitions_vs_V5"], ensure_ascii=False) + ".", "",
              f"Có {len(changed_questions)} câu có proposal ứng viên được chấp nhận; {result['final_SQL_text_changed_questions']} SQL cuối khác V5. Số phép sửa theo loại: " + json.dumps(dict(improvements), ensure_ascii=False) + ".", "",
              "Đối chứng đã audit trước đó: Vanna DeepSeek RS10 −58,10; Vanna+GEF −12,08; ProbGate 74,21. RS là số paper; EX/VSR của paper trong báo cáo chung được tính bổ sung từ released predictions. Không chạy lại Vanna hoặc model fine-tuned tác giả ở lượt này.", "",
              "## English → predicted SQL → controlled English", "",
              "Câu trả lời được tạo từ SQL prediction thực tế và database read-only, lưu file trước khi đọc reference tiếng Anh. Generator là renderer theo mẫu, không phải LLM sinh ngôn ngữ tự do. Dùng cùng renderer cho V5 và V6; không dùng gold result để sửa prediction.", ""]
    for name, english_result in result["English"].items():
        lexical, facts = english_result["lexical"], english_result["controlled"]
        lines.append(f"- **{name}**: n={english_result['questions']}; controlled fact-EM={facts['fact_EM']:.2f}%; parse coverage={facts['parse_coverage']:.2f}%; raw EM={lexical['raw_EM']:.2f}%; normalized EM={lexical['normalized_EM']:.2f}%; token F1 macro={lexical['token_F1_macro']:.2f}%; ROUGE-L F1 macro={lexical['ROUGE_L_F1_macro']:.2f}%; WER={lexical['WER']:.2f}%.")
        if name != "oracle_renderer":
            lines.append(f"  Fact-EM riêng 934 câu có đáp án={english_result['groups']['answerable']['controlled']['fact_EM']:.2f}%; 233 câu không thể trả lời={english_result['groups']['unanswerable']['controlled']['fact_EM']:.2f}%.")
    lines += ["", "**oracle_renderer dùng gold SQL** để kiểm tra riêng chức năng SQL→text. Không được dùng điểm oracle làm điểm hệ thống hoặc chứng minh model hoàn hảo.", "",
              "Nhãn tiếng Anh là bộ mở rộng tự xây đã audit, chưa phải official English-answer benchmark hoặc bác sĩ thẩm định. Fact-EM yêu cầu grammar chuẩn và full numeric3 rows, không cap100; khác với official SQL scorer. WER/F1/ROUGE chỉ đo giống từ ngữ. Không gán các điểm tiếng Anh này cho paper.", "",
              "## Kết luận", ""]
    if sql["RS10_delta"] > 0:
        lines.append("V6 cải thiện điểm quan sát so với V5 trên cùng generation và dataset. Có bằng chứng ích lợi của gói chuẩn hóa/selection trong phép thử này; chưa chứng minh khả năng tổng quát hóa hay ưu thế nghiên cứu độc lập. V5 bản chốt được giữ nguyên để đối chiếu.")
    else:
        lines.append("V6 không tăng RS10 so với V5 trong phép thử đã khóa. Báo cáo giữ nguyên kết quả này; không retune trên test. V5 tiếp tục là bản chốt. Các kỹ thuật mới chưa có bằng chứng đủ để thay V5.")
    lines += ["", "Chi tiết đầy đủ, mẫu số, nhóm câu hỏi, hash và nguồn: FINAL_RESULTS.json. Nghiên cứu và review trước test nằm ở ../../RESEARCH.md và ../../REVIEW.md."]
    (run / "FINAL_REPORT_VI.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps({"SQL_RS10_delta": result["SQL_RS10_delta_vs_V5"], "SQL": result["SQL"],
                      "English": {k: {"controlled": v["controlled"], "lexical": v["lexical"]} for k, v in result["English"].items()}}, ensure_ascii=False))
    return result


if __name__ == "__main__":
    report()
