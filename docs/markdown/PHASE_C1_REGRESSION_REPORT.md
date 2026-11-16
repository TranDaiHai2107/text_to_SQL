# Phase C.1 regression — 14/11/2026

**Offline test result: 71 PASS / 71 selected tests.** Command (project root, `PYTHONPATH=src`):

```powershell
python -m pytest tests/test_phase_c1_pilot.py tests/test_phase_b_integration.py tests/test_controlled_execution.py tests/test_bigquery_execution_prep.py tests/test_clinsql_foundation.py tests/test_clinsql_offline_workflows.py tests/test_agentic_evidence.py tests/test_agentic_selection.py -q --basetemp .pytest_phase_c1_verified
```

`python paper_sources.py` PASS: CLINSQL `1d819960eb3ce3ac0e9beb4e801810a05735fd58`, MAC-SQL `31a9df5e0d520be4769be57a4b9022e5e34a14f4`, SDE-SQL `e425408fcb13d69b0bd15f917b819591805a8973`; key-file hashes giữ nguyên. `python -m compileall -q src/ehrqa/clinsql src/ehrqa/cli/phase_c1_pilot.py` PASS. `git diff --check` exit 0 (chỉ có cảnh báo CRLF trong file cũ).

## Contract checks

- `tests/test_phase_c1_pilot.py`: 9 PASS. Case selection 152/38 và 5 development cases, plan-only không tạo request; Responses message shape/`store=False`/usage/model; persistent API budget và ambiguous timeout; Phase A approval bị từ chối; fake real CoT route qua SQLGlot adapter, result artifact 2 rows/NULL, checkpoint resume; BigQuery result-byte cap trả incomplete; pandas CSV output khớp đường native trên dữ liệu tổng hợp; MAC pruning source rule; retention chỉ xóa khi đến hạn.
- Phase B + controlled execution tests vẫn xác minh SQL Guard/allowlist, multi-row/typed result, bytes cap, timeout/permission translation, restricted storage, SQL budget ledger, bốn workflows mock, evaluation staging và source-independent contracts.
- `phase-c1-pilot plan --api-budget docs/PHASE_C1_API_BUDGET_DRAFT.json --sql-budget docs/PHASE_C1_SQL_BUDGET_DRAFT.json` PASS; báo `openai_requests_sent=0`, `bigquery_patient_queries_executed=0`, API key present=false và cost preview. Không chạy `execute`.

## Research validity và leakage checks

- Pilot manifest chỉ dùng `load_official_questions` đọc `query_*.txt` của validation; không mở gold SQL, reference results hoặc rubrics để chọn case. Index schema được tái tạo từ manifest INFORMATION_SCHEMA, không có SQL answers. 38 internal-check và 443 test không được dùng để chọn case/prompt.
- Real inference nhận question text, schema DDL, và khi cần previous model SQL + lỗi redacted. Result rows chỉ vào `ResultArtifactStore` có ACL, không vào `MeteredModel` hay application logs. Rubrics chỉ được copy trong lệnh `stage` sau khi prediction đã lưu.
- Phase A approval không tương thích `BenchmarkExecutionApproval`. Approval Phase C.1 kiểm tra case IDs, hashes, reader principal, US datasets, validity window, limits và budget-file hashes. IAM vẫn `READ_ONLY_LIKELY_WITH_APPROVED_RISK`, không được nâng nhãn.
- Output incomplete, budget/permission/timeout và model request outcome unknown dừng có kiểm soát; không đưa partial result vào scorer, không auto-retry, không tự xóa case khỏi denominator.

## Những phần chưa kiểm chứng

Chưa có `OPENAI_API_KEY` trong Python process kiểm tra nên chưa thể thử GPT-5-mini availability, API response thật hoặc snapshot thực tế. Không truy vấn BigQuery MIMIC trong Phase C.1; live ADC/ACL và row/byte behavior phải được xác minh tại thời điểm chạy. Pandas CSV parity đã thử với scalar/NULL/Decimal/duplicate tổng hợp, chưa chứng minh parity của Arrow DATE/TIMESTAMP/ARRAY/STRUCT hoặc scorer/judge trên kết quả thật. Judge chính thức và budget riêng chưa bật. Legacy PostgreSQL/ứng dụng tiếng Việt nằm ngoài phạm vi; toàn bộ test suite chưa được tuyên bố PASS.
