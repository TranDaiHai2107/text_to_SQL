# Phase C.1 — GPT-5-mini + CLINSQL validation pilot

**Final live update 14/11/2026:** Phase C.1 technical pilot **PASS 5/5** across
versioned v4/v5 approvals. The user's separate v5 decision authorized
16 GiB/SQL and 160 GiB aggregate for exactly these five cases. Five complete
BigQuery artifacts and job IDs passed hash/ACL audit, 83/83 selected offline
tests passed, and the SQL ledger has zero pending jobs. No official CLINSQL
score or judge has run. See `GPT5_MINI_LIVE_PILOT_RESULTS.md`. All earlier
`0/5`, partial and approval-missing statements below are historical.

**Live update 14/11/2026:** Phase C.1 risk, 256 MiB/SQL, 3.75 GiB aggregate
and seven-day artifact retention were approved. The live pilot has begun but
is `PARTIALLY_COMPLETED`: no case has completed BigQuery execution. See
`GPT5_MINI_LIVE_PILOT_RESULTS.md` for actual v1/v2/v3 attempts, token usage,
the unknown API request and the 7.91 GiB dry-run estimate that exceeded the
approved SQL cap. Historical readiness text below is superseded by this
measured status. No official score exists.

**Update 14/11/2026:** OpenAI model retrieval and one nonclinical Responses
request now PASS; details and actual token/cost ledger are in
`GPT5_MINI_ACCESS_CHECK.md`. `.env` now pins the GPT-5-mini snapshot and BigQuery
US settings, is loaded by `run.py`, and has private Windows ACL. API policy now
matches the user's November authorization (`UNLIMITED_RESEARCH_NOV_2026`), with
no aggregate USD hard cap; the five-case pilot still has algorithmic call/token
bounds. Historical statements below describing an absent API key or the former
$0.25 API cap are superseded by this update.
Phase C.1 BigQuery approval and aggregate budget remain missing; pilot is 0/5.

Ngày 14/11/2026. **Trạng thái: CODE_READY_OFFLINE; chưa đạt `READY_FOR_5_CASE_PILOT` và chưa chạy pilot có phí.** OpenAI SDK 3.49.0 và BigQuery SDK 3.47.0 có trong `.venv_papers/clinsql`. `OPENAI_API_KEY` **không hiện diện trong process kiểm tra**, nên quyền truy cập GPT-5-mini của tài khoản chưa xác minh. Phase A approval không dùng được cho pilot. Không có OpenAI request, BigQuery patient query hay CLINSQL judge call trong nhiệm vụ này.

## Code đã triển khai

- `openai_provider.py`: Responses API, đúng một user message chứa original CoT prompt; `max_output_tokens=2048`, `store=False`, timeout, SDK `max_retries=0`. Ghi returned model, response ID, usage và latency. Lỗi mất kết nối/timeout có outcome không rõ được giữ ở ledger và không retry tự động. `n>1` bị khóa để không âm thầm biến SDE 9-candidate thành chín lượt API khác native.
- `pilot_api_budget.py`: SQLite reserve token/cost trước request, reconcile bằng usage thật; reservation chưa rõ sau crash vẫn chiếm cap. Giá input/output trong proposal lấy từ [trang GPT-5 mini chính thức của OpenAI](https://developers.openai.com/api/docs/models/gpt-5-mini), không tính cached-input discount khi giữ cap. Model page xác nhận Responses endpoint, text I/O và snapshot; tài khoản cụ thể chưa được xác nhận. [Thông báo deprecation chính thức](https://developers.openai.com/api/docs/deprecations) ghi GPT-5-mini và snapshot `gpt-5-mini-2025-08-07` có ngày shutdown 11/12/2026; cần chốt dùng alias hay snapshot cho pilot, không tự đổi sang model khác.
- `pilot_cases.py` và `data/clinsql/pilot_5_validation_development_v1.json`: chỉ đọc 190 file `query_*.txt`, chia theo seed `clinsql-2026-v1` thành 152 development/38 internal-check. Chọn cố định 2 easy, 2 medium, 1 hard ở năm domain khác nhau theo SHA-256 của ID, không xem gold/reference/đáp án model. Pilot manifest SHA-256: `f8935ddf79131560ecc10023e7db034d61a15b1546cfe1952d9cc152e493680f`.
- `benchmark_approval.py`: approval Phase C.1 riêng, khóa principal reader, project/datasets US, manifest/index và năm case, model, thời gian, cap, retention, risk acceptance `READ_ONLY_LIKELY_WITH_APPROVED_RISK`, hash hai budget files. Phase A approval bị từ chối. SQL động không thể khóa hash trước generation; SQLGlot Guard, allowlist, dry run, ADC reader, bytes cap và case scope vẫn bắt buộc.
- `real_cot_runner.py` và `phase_c1_pilot.py`: một case/lệnh, marker trước API, log fingerprint câu/model/schema/index/code, chạy CoT original prompt/cleaner và tối đa hai refinement, lưu multi-row artifact có ACL, resume chỉ đọc metadata. `stage` là bước riêng sau inference, mới đọc rubric files công khai và chuẩn bị input official scorer; **không gọi judge**. `retention` kiểm tra hạn và chỉ xóa artifact đến hạn khi người vận hành gọi `--delete-expired`.
- `bigquery_client.py`, `bigquery_adapter.py`, `execution_modes.py`, `benchmark_backend.py`: benchmark profile riêng, max rows và result bytes, đánh dấu incomplete thay vì đưa partial output vào scorer. Patient execution mặc định tắt; chỉ mở qua approval Phase C.1 hợp lệ. `evaluator.py` dùng pandas CSV như đường lưu output của CLINSQL gốc; test synthetic multi-row/NULL/duplicate PASS. ARRAY/STRUCT và dtype Arrow/BigQuery thật vẫn cần kiểm chứng trước official scoring.

## Năm case được khóa

1. `Diagnostic_Procedures/easy_level_queries/058`
2. `Vital_Signs_Monitoring/easy_level_queries/044`
3. `Laboratory_Results_Analysis/medium_level_queries/079`
4. `Medication_Management/medium_level_queries/012`
5. `Patient_Demographics_and_Admissions/hard_level_queries/058`

Domain, difficulty, question hash và rule/seed đầy đủ trong pilot manifest. Các generation prompts đầu tiên có upper bound UTF-8 khoảng 10,994–11,126 input tokens mỗi câu; đây là reservation bound, **không phải usage đo từ API**.

## Budget preview để phê duyệt, chưa phải ngân sách được cấp

Đề xuất ở `docs/PHASE_C1_API_BUDGET_DRAFT.json` và `docs/PHASE_C1_SQL_BUDGET_DRAFT.json`: tối đa **15** model calls (5 câu × 3 attempts), **600,000** input tokens, **30,720** output tokens, API cap **$0.25**. Theo [giá GPT-5 mini](https://developers.openai.com/api/docs/models/gpt-5-mini) $0.25/1M input và $2/1M output, trường hợp dùng hết hai token caps ước **$0.21144** trước cache/tax; cap $0.25 vẫn là trần kiểm soát. SQL: **256 MiB/query**, 3 calls/câu, **3.75 GiB** toàn pilot, timeout **120 giây/query**, 10,000 rows và 16 MiB serialized result/query. Theo [BigQuery on-demand US $6.25/TiB](https://cloud.google.com/bigquery/pricing), 3.75 GiB tương đương khoảng **$0.02289** trước free tier/billing plan/tax. Tổng trần lý thuyết nếu cả hai cap dùng hết khoảng **$0.27289**; đây không phải invoice. Các cap này là **đề xuất**, không tự áp dụng khi chưa có approval. SQL cụ thể chỉ có sau generation nên không thể dry run/cost estimate theo câu trước pilot.

Nếu SQL vượt bytes/rows/result bytes/timeout, dừng và gắn `BUDGET_EXCEEDED`, `INCOMPLETE_RESULT` hoặc `TIMEOUT`; không cho 0 điểm model, không tự nâng cap, không loại case khỏi denominator. Native CLINSQL dùng 50 GB và 300 giây; profile pilot 256 MiB/120 giây là adaptation có thể censor và phải được kiểm tra trên validation trước khi báo reproduction/score.

## Nội dung đưa tới GPT-5-mini

Lượt đầu: **chính xác câu hỏi tiếng Anh CLINSQL validation** đặt vào `build_generation_prompt` từ checkout CLINSQL gốc, cộng DDL BigQuery của 31 bảng từ manifest. Lượt refinement nếu SQL sai: câu hỏi, DDL, SQL model vừa sinh và thông báo lỗi đã redacted qua `build_refinement_prompt` gốc. Không truyền patient rows, query results, gold SQL, reference CSV hoặc test rubric. Không dùng Vietnamese processing. Redaction làm thay đổi thông tin lỗi so với native baseline và được công bố trong `BASELINE_FIDELITY_PROGRESS.md`.

## Điều kiện còn thiếu để chạy case đầu tiên

1. Người phụ trách xác nhận model alias `gpt-5-mini` hay snapshot `gpt-5-mini-2025-08-07`, cùng data handling và hạn giữ artifact. Hiện chưa có API key trong process; thiết lập qua biến môi trường an toàn, không gửi key trong chat. Cần xác minh account/model access bằng request có phí sau approval; SDK signature/local docs chưa chứng nhận quyền account.
2. Xem và chốt hai budget drafts, lưu bản đã chốt dưới `results/restricted` và tính SHA-256 **của đúng file bytes**. Điều chỉnh rows/bytes/time nếu có cơ sở; giữ cùng constraints cho các method trong so sánh sau này.
3. Điền `docs/PHASE_C1_APPROVAL_DRAFT.json` thành `results/restricted/phase_c1_approval.json`: tên/vai trò/thẩm quyền thật, risk acceptance riêng cho Phase C.1, UTC hiệu lực, hai budget hashes, result storage policy và retention days. Draft hiện không hợp lệ và không thể chạy. Không tuyên bố `VERIFIED_READ_ONLY` hoặc Organization clearance.
4. Chạy source-lock/ADC/ACL preflight qua CLI; kiểm tra còn `OPENAI_API_KEY` trong process chạy, không có `GOOGLE_APPLICATION_CREDENTIALS` override. Official scorer/judge có budget riêng và chỉ chạy sau phê duyệt riêng.

## Lệnh chính xác

Plan không tạo API/BigQuery jobs:

```powershell
.\.venv_papers\clinsql\Scripts\python.exe run.py phase-c1-pilot plan --api-budget docs/PHASE_C1_API_BUDGET_DRAFT.json --sql-budget docs/PHASE_C1_SQL_BUDGET_DRAFT.json
```

Sau khi điền/cấp approval hợp lệ và đặt hai budget files đã khóa tại `results/restricted`, chỉ chạy **một case** mỗi lệnh:

```powershell
.\.venv_papers\clinsql\Scripts\python.exe run.py phase-c1-pilot execute --case-id 'Diagnostic_Procedures/easy_level_queries/058' --approval results/restricted/phase_c1_approval.json --api-budget results/restricted/phase_c1_api_budget.json --sql-budget results/restricted/phase_c1_sql_budget.json --execute-approved
```

Đọc checkpoint hoặc stage evaluation, không gọi model lại:

```powershell
.\.venv_papers\clinsql\Scripts\python.exe run.py phase-c1-pilot resume --case-id 'Diagnostic_Procedures/easy_level_queries/058'
.\.venv_papers\clinsql\Scripts\python.exe run.py phase-c1-pilot stage --case-id 'Diagnostic_Procedures/easy_level_queries/058'
.\.venv_papers\clinsql\Scripts\python.exe run.py phase-c1-pilot retention
```

Khi artifact đến hạn, người phụ trách chạy thủ công `phase-c1-pilot retention --delete-expired`; chưa có tác vụ tự động. Nếu marker tồn tại nhưng log thiếu, API request outcome unknown, IAM PermissionDenied, budget/timeout, output incomplete, source/hash drift hoặc ACL không đạt: **dừng, điều tra và không auto-retry**.
