# Clinical Text-to-SQL trên CLINSQL (MIMIC-IV v3.1, BigQuery)

Khóa luận: so sánh hệ thống đề xuất **Ours** (multi-layer RAG + agentic self-correction) với hai baseline tái hiện từ paper gốc trên benchmark CLINSQL (EACL 2026):

| Phương pháp | Code | Trạng thái |
| --- | --- | --- |
| CLINSQL CoT + self-refinement | `src/ehrqa/clinsql/cot.py`, `cot_runner.py` | **Đã khóa** (`BASELINE_LOCK.json`) |
| SDE-SQL | `src/ehrqa/clinsql/baselines/sde_*.py` | **Đã khóa** (`BASELINE_LOCK.json`) |
| Ours | `src/ehrqa/agentic/`, `src/ehrqa/clinsql/proposed.py` | Đang phát triển (v10) |

Mọi phương pháp dùng cùng một model `gpt-5-mini-2025-08-07` (reasoning effort `medium`), cùng BigQuery reader, cùng giới hạn. Không gửi dòng kết quả bệnh nhân cho LLM (`SEND_RESULTS_TO_LLM=false`).

## Cấu trúc

- `src/ehrqa/agentic/`: pipeline Ours (linker, sinh SQL, validator SQLGlot, repair, lựa chọn).
- `src/ehrqa/clinsql/`: adapter BigQuery, ledger ngân sách API/SQL, provider OpenAI, judge rubric, baseline.
- `scripts/run_validation_v10.py`: chạy và chấm 3 phương pháp trên 190 câu validation (test 443 câu niêm phong).
- `scripts/score_execution_accuracy.py`: EX strict/relaxed so với CSV gold.
- `external/`: source gốc của paper (ghim commit trong `PAPER_SOURCE_LOCK.json`, không sửa).
- `data/`: manifest schema, index, corpus few-shot (chỉ dev), từ điển ICD công khai CMS.
- `results/restricted/`: kết quả (ACL riêng tư, không commit).
- `reports/`, `research_notes/`: phân tích lỗi và tài liệu nghiên cứu.

## Chấm điểm

1. **Tier 1:** Execution Accuracy xác định (strict/relaxed) so với CSV gold.
2. **Tier 2:** CLINSQL rubric SQL Score với judge **adapted** gpt-5-mini (không phải judge official Azure gpt-5-chat).
3. Execution Score của paper không tính (`UNSCORED_DATA_EGRESS`) vì cần gửi dòng kết quả cho LLM.

## Chạy

```powershell
.\.venv_papers\clinsql\Scripts\python.exe -m pytest -q
$env:SEND_RESULTS_TO_LLM = 'false'
.\.venv_papers\clinsql\Scripts\python.exe scripts\run_validation_v10.py --execute --workers 8
.\.venv_papers\clinsql\Scripts\python.exe scripts\run_validation_v10.py --summarize-only results\restricted\<root>
```

Mỗi lần chạy cần approval/credit evidence còn hiệu lực và chỉ chạy trong trần ngân sách đã được duyệt. Xem `environment/README.md` để dựng môi trường.
