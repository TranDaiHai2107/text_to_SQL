# Trạng thái triển khai theo yêu cầu nghiên cứu CLINSQL

**Phase C.2 hiện hành 14/11/2026:** audit 5/5 saved CLINSQL CoT predictions;
native scorer CSV staging/parser 5/5 PASS trong thư mục restricted tạm đã xóa;
diagnostic validation strict result shape/name match **0/5**, không phải
official score. Người phụ trách xác nhận **chưa cho phép truyền result rows
tới Azure GPT-5-Chat**, nên SQL Score/Execution Score chính thức là
`OFFICIAL_SCORE_NOT_AVAILABLE`; không có judge, GPT-5-mini hay BigQuery call
mới. MAC-SQL đã sửa ChatManager về đúng 3 agent turns; SDE-SQL có source-level
subquery/probe parity tiến triển; Ours có frozen few-shot corpus 145 ví dụ
development hợp lệ. **91/91 selected offline regression tests PASS**; pilot
5/5 đã nhập vào durable checkpoint và test 443 vẫn sealed. Xem
`PILOT_5_ACCURACY_EVALUATION.md`, các file `*_FIDELITY_FINAL.md` và
`results/phase_c2_status.json`. MAC/SDE/Ours **chưa có live pilot**;
full validation/test và official evaluation chưa chạy.

**Trạng thái hiện hành 14/11/2026:** Phase C.1 CLINSQL CoT + Self-Refinement
đã hoàn tất **5/5 lượt thực thi kỹ thuật** trên BigQuery MIMIC-IV v3.1 bằng
`gpt-5-mini-2025-08-07`. Năm result artifacts đầy đủ đã qua kiểm tra hash,
ACL và hạn lưu 7 ngày; 5 SQL jobs billed 20,081,278,976 bytes (18.702 GiB),
6 API calls ở các lượt thành công, 83/83 selected offline tests PASS. Xem
`GPT5_MINI_LIVE_PILOT_RESULTS.md` và `results/phase_c1_pilot_audit.json`.
**Chưa chạy official SQL Score, Execution Score, judge, MAC-SQL, SDE-SQL, Ours
trên API thật hoặc full benchmark.** Các đoạn 0/5, chưa có API/BigQuery và
budget thiếu bên dưới là lịch sử trước pilot, không còn là trạng thái hiện hành.
Phase C.1 approval 16 GiB/SQL và 160 GiB tổng chỉ áp dụng năm case đã khóa.

**Phase C.1 offline 14/11/2026:** đã có GPT-5-mini Responses transport, API/SQL budget và approval riêng cho pilot, real CoT runner một case/lệnh, 5-case development manifest, evaluation staging và manual retention. **71/71 selected tests PASS**, source lock PASS. API key không hiện diện trong process kiểm tra; chưa gọi OpenAI, BigQuery patient SQL hoặc judge. Approval/budget/data policy chưa được người phụ trách chốt nên **chưa đạt READY_FOR_5_CASE_PILOT**. Xem `PHASE_C1_REAL_PILOT_READINESS.md`, `BASELINE_FIDELITY_PROGRESS.md`, `PHASE_C1_REGRESSION_REPORT.md`. Các mục bên dưới là lịch sử tại thời điểm viết.

**Phase B offline 13/11/2026:** manifest BigQuery 31 bảng đã sinh Schema RAG index khóa hash; shared benchmark backend, typed multi-row artifact, persistent SQL budget ledger và checkpoint/resume đã có test. Hai câu validation công khai × bốn phương pháp chạy mock end-to-end; **62 regression tests PASS** và source lock PASS. Execution benchmark thật vẫn đóng, không dùng approval Phase A. MAC-SQL/SDE-SQL còn fidelity và data-policy gaps; GPT-5-mini pilot chưa được mở. Xem `PHASE_B_INTEGRATION_REPORT.md`. Các mục cũ bên dưới là lịch sử tại thời điểm viết.

**Phase A thực tế 13/11/2026: PASS 4/4.** Bằng ADC impersonation reader, bốn SQL smoke trả `364627`, `94458`, `94458`, `0`; kết quả khớp metadata/reference/quan hệ JOIN. Tổng billed **40 MiB**; 53 offline regression tests PASS. Approval là `READ_ONLY_LIKELY_WITH_APPROVED_RISK` cấp project, không tuyên bố Organization IAM đã được kiểm chứng. Scalar artifacts lưu trong `results/restricted`, hạn 7 ngày và xóa thủ công bằng CLI; chưa đến hạn. **Chưa gọi GPT-5-mini/judge, chưa chạy benchmark hoặc migration tiếng Việt; MAC-SQL/SDE-SQL chưa đủ fidelity.** Xem `PHASE_A_EXECUTION_RESULTS.md` và `RESEARCH_VALIDITY_REGRESSION_REPORT.md`. Các đoạn trạng thái cũ bên dưới là lịch sử.

**Cập nhật metadata integration 12/11/2026:** BigQuery backend cuối cùng áp dụng cho cả dự án; migration hệ thống tiếng Việt được hoãn. ADC đã hoạt động: hai datasets ở `US`, đủ 31 bảng; manifest BigQuery thật có hash và kiểm tra critical columns/SQLGlot PASS. Xem `BIGQUERY_METADATA_INTEGRATION_REPORT.md`. Chưa xác minh toàn bộ effective IAM hoặc chạy patient-data SQL; không gọi OpenAI/judge.

**Cập nhật SQL execution preparation 12/11/2026:** năm SQL smoke dry run PASS dưới ADC impersonation `kltn-sql-reader`, 0 SQL được thực thi. 31/31 bảng trả quyền đọc và không trả quyền ghi khi thử quyền; direct dataset entries là `READER`. Project IAM policy trả 403, nên chưa xác minh độc lập toàn bộ quyền kế thừa và execution vẫn BLOCKED. Xem `BIGQUERY_SQL_EXECUTION_PREP_REPORT.md`. Result artifacts đã có interface tách khỏi logs nhưng ACL MIMIC thật chưa xác minh.

**Cập nhật 13/11/2026:** người dùng xếp IAM `READ_ONLY_LIKELY`, phê duyệt ngoại lệ đúng một `SELECT 1 AS smoke_constant`. Job `4b64ef9e-0d0e-494f-b902-72a56f1f2e70` PASS, trả 1, billed 0 bytes, server latency 0.159 giây. General execution guard vẫn tắt; bốn SQL MIMIC chưa chạy và tiếp tục BLOCKED.

**Gate MIMIC SQL smoke 13/11/2026:** project hierarchy/IAM policy API trả 403 với service account; Organization/Folder inheritance chưa thể xác minh, Policy Troubleshooter Owner=`Unknown`. Windows ACL `results/restricted` PASS và test artifact tổng hợp đã xóa; logs không cho capture raw rows với database thật. Xem `MIMIC_SQL_EXECUTION_GATE_REPORT.md`. Bốn SQL MIMIC vẫn BLOCKED chờ bằng chứng IAM đầy đủ hoặc quyết định chấp nhận rủi ro riêng.

Kiểm kê ngày 12/11/2026 sau đợt phát triển offline. Phân biệt **source gốc**, **workflow chạy bằng mock**, và **thực nghiệm trên môi trường thật**. Đã có inference/evaluation giả lập trong unit tests; **chưa gọi OpenAI, BigQuery, LLM judge hoặc chạy benchmark test**, nên chưa có điểm để so sánh.

## Nguồn benchmark, paper và môi trường

- **Đã làm:** clone source chính thức CLINSQL, MAC-SQL, SDE-SQL vào `external/`; khóa commit/tree và hash các file chính trong `PAPER_SOURCE_LOCK.json`. `python paper_sources.py` xác nhận 190 câu validation và 443 câu test của CLINSQL. Benchmark công khai đã nằm trên máy; không phải chỉ chờ BigQuery để tải benchmark.
- **Đã làm:** cài ba virtual environment riêng trong `.venv_papers/`. MAC-SQL và SDE-SQL cài requirements gốc; CLINSQL cài subset cần cho proprietary GPT-5-mini và scorer. Lưu package snapshot trong `environment/locks/`. Cả ba `pip check` sạch và native CLI mở được `--help`. Đây mới là kiểm tra import/CLI, chưa xác nhận inference.
- **Đã làm:** đối chiếu luồng thuật toán với code gốc tại `PAPER_ALGORITHM_AUDIT.md`. Source gốc không bị sửa. MAC-SQL có nhánh oracle schema; SDE-SQL có đường dùng gold trong entrypoint, ép đọc examples file không có trong checkout, và dùng probes/self-consistency. Các nhánh này phải được xử lý, ghi adaptation và kiểm chứng trước khi báo reproduction.

## Năm quyết định protocol đã chốt

1. **Tiếng Anh — chạy được bằng mock:** adapter nhận câu hỏi tiếng Anh nguyên bản; runner offline dùng cùng `Question` cho bốn phương pháp. Code dịch/diễn giải tiếng Việt vẫn còn trong ứng dụng cũ và không nằm trong runner CLINSQL.
2. **Validation/test — đã có guard offline:** adapter đọc `query_*.txt`, kiểm tra đủ 190 validation, chỉ trả question/ID/domain/difficulty, tạo SHA-256 và chặn test mặc định; seed hiện tại chia 152 development/38 internal-check. `FewShotIndex` chỉ nhận ví dụ validation-development, loại chính câu đang hỏi/câu cùng text và hỗ trợ danh sách hash SQL cần chặn. Chưa có retrieval corpus được phê duyệt hoặc manifest khóa index cho lượt thật; không đọc gold test để lọc.
3. **Dữ liệu/probes — mock đã chạy:** interface chung, BigQuery adapter read-only/dry-run/cap và preflight plan 22 HOSP/9 ICU. Mock schema hiện hoàn toàn tổng hợp; manifest thật chờ INFORMATION_SCHEMA. SDE mock chạy probe hai giai đoạn; chưa kiểm tra IAM MIMIC hoặc policy truyền evidence thật, và chưa gọi BigQuery.
4. **Baselines/điều kiện so sánh — workflow mock, chưa có điểm:** CLINSQL CoT giữ prompt/cleaner gốc và hai refinement; MAC-SQL mock chạy Selector/Decomposer/Refiner; SDE-SQL mock chạy hai tầng probes, 9 candidates và refinement. Các port MAC/SDE còn khác source ở prompt/selection/judge/value sampling nên **không được dùng báo điểm như reproduction**. `ExperimentConfig` giữ model ID dự kiến GPT-5-mini; chưa xác minh model snapshot, database hay judge thật.
5. **Mức độ tái hiện và scorer — có nền offline, chưa xác nhận fidelity:** `BASELINE_ADAPTATION.md` ghi khác biệt. Đã có staging đúng tên file `query_*/sql_*/result_*` và rubric cho bước evaluation riêng, mock scorer trả SQL Score/Execution Score và cho chấm lại prediction đã lưu. Chưa khởi tạo judge chính thức hoặc kiểm tra điểm tương đương native scorer trên lượt thật.

## Bảy bước triển khai đã yêu cầu

1. **Audit code/EHRSQL: đã lập inventory đường legacy.** Xem `LEGACY_DEPENDENCY_AUDIT.md`; tách contracts, security và logging trung lập vào `ehrqa.text2sql`. CLI PostgreSQL/Mini đã tắt, file schema và script build Mini đã xóa; source app cũ vẫn nằm trong repo nhưng không là runtime benchmark. Cần xác nhận runtime boundary sau khi nối provider thật.
2. **Benchmark adapter CLINSQL: hoàn thành phần offline.** Đọc layout source gốc, kiểm tra số câu, fingerprint, test gate; lệnh `python run.py clinsql-inspect --official-root external/clinsql_official` không gọi API/DB.
3. **Database/evaluation interface chung: đã có mock và staging; thật chờ xác minh.** `BigQueryConfig`, `BigQueryClient` lazy, preflight metadata/row-count/dry-run script đã chuẩn bị. Evaluation adapter gọi scorer được tiêm vào trên predictions đã lưu; chưa gọi judge trả phí.
4. **Baseline CLINSQL CoT: workflow mock đã chạy.** Prompt/cleaner từ source gốc, test ba attempts thành công; chưa có lượt GPT-5-mini/BigQuery và chưa xác minh output tương đương native runner.
5. **Chuyển hệ thống đề xuất: end-to-end mock đã chạy.** Schema RAG, callback ICD dictionary, FewShotIndex validation-development, generation, BigQuery SQL validation và technical self-correction đã được kiểm tra bằng synthetic data. CLI ứng dụng PostgreSQL/Mini đã tắt; ICD/few-shot corpus thật và schema BigQuery đã xác minh chưa có.
6. **MAC-SQL và SDE-SQL: port workflow mock, fidelity chưa hoàn chỉnh.** Có agent/probe stages và unit tests; thiếu parity của pruning/value sampling, generation/refinement prompts, candidate selection/judge gốc. Không tuyên bố tái hiện hoàn chỉnh hay cho chạy thật từ offline runner.
7. **Pilot validation/test: chưa thực hiện.** Chưa gọi API quy mô lớn, chưa chạy probes MIMIC, chưa chạy test chính thức. Chưa có SQL Score, Execution Score, chi phí/query hoặc kết luận hệ thống đề xuất tốt hơn.

## Kiểm chứng đã thực hiện và bước còn thiếu

`python paper_sources.py` qua; adapter đọc 190 validation và chia 152/38. Sau readiness audit, **35 test offline liên quan CLINSQL, BigQuery/security, agentic evidence/selection, RAG, logging và baseline mock qua**; hai transport tests qua riêng khi chạy ngoài sandbox Windows. Trong sandbox, event loop treo tại `socket.socketpair` trước HTTP mock. Ba môi trường paper trước đó qua `pip check` và native `--help`. Toàn bộ test suite hiện **FAIL ở collection** của bốn module legacy PostgreSQL/Mini còn import file schema Mini đã xóa; xem `BIGQUERY_READINESS_REPORT.md`.

Trước pilot cần nối BigQuery MIMIC-IV v3.1 và nạp schema manifest thật; xác minh quyền và dữ liệu được phép gửi LLM; hoàn thiện model transport, log/resume và scorer chính thức; kiểm chứng fidelity MAC/SDE cùng giá trị probe; rồi khóa model/prompt/code/config. Runner offline chủ động chỉ nhận `MockLLM`/`MockBigQuery`, nên không thể vô tình gọi API có phí.

## File và module mới của đợt offline

- `src/ehrqa/text2sql/`: contracts database/evaluation, danh sách hàm SQL cấm và logging/ước tính chi phí không phụ thuộc benchmark.
- `src/ehrqa/clinsql/metadata.py`, `config.py`, `bigquery_client.py`: inventory 31 bảng, config tập trung, dataset INFORMATION_SCHEMA và manifest version/hash; client lazy, data execution tắt mặc định. Chưa gọi kết nối thật.
- `src/ehrqa/clinsql/offline.py`, `retrieval.py`, `runner.py`: mock LLM/DB, few-shot development-only, ICD dictionary callback và runner validation mock-only.
- `src/ehrqa/clinsql/baselines/mac_sql.py`, `sde_sql.py`, `source_templates.py`: stage ports kiểm thử offline, không được coi là reproduction hoàn chỉnh.
- `src/ehrqa/clinsql/evaluator.py`: staging output tương thích tên file scorer và đánh giá từ predictions đã lưu bằng scorer được tiêm vào.
- `src/ehrqa/cli/bigquery_preflight.py`: mặc định in plan 22 HOSP/9 ICU không kết nối; chỉ khi có `--execute-metadata` mới đọc 4 truy vấn INFORMATION_SCHEMA và table metadata, không thực thi patient SELECT. Smoke tests chưa được bật.
- `src/ehrqa/clinsql/proposed.py`, `cot_runner.py`, `interfaces.py` và `src/ehrqa/agentic/schema.py`: nối RAG được phép, dừng CoT khi generation rỗng, chuyển interface/security sang core trung lập; `run.py` đăng ký lệnh preflight. Không đổi đường production PostgreSQL.
- `LEGACY_DEPENDENCY_AUDIT.md`, `tests/test_clinsql_offline_workflows.py`: ranh giới legacy và kiểm thử tự động.

## Còn thiếu và cần dữ liệu thật

- **MAC-SQL:** parity của selector pruning/column-value sampling, format schema/FK, prompt BigQuery và thứ tự agent/refiner so với native.
- **SDE-SQL:** generation và prompt sửa lỗi/kết quả rỗng lấy từ source rồi đổi riêng phần SQLite dialect; còn cần kiểm chứng parity sau adaptation, phân rã subquery/probe refinement đầy đủ, execution-consistency selection/judge_target ba phiếu và chính sách probe evidence. Runner mới không nhận gold; native code vẫn được giữ nguyên trong checkout.
- **Evaluator:** gọi scorer CLINSQL với judge thật, xác minh CSV/result edge cases và so sánh output/score với native trên pilot validation. Mock scorer hiện không cho điểm benchmark.
- **Logging/resume:** log mock có SQL, trạng thái, attempt, token, latency và cost ước tính từ bảng giá do người dùng cung cấp; cần kiểm tra usage/cost/model ID trả từ API thật, persistence khi lỗi giữa chừng và resume đa phương pháp trước pilot.
- **BigQuery:** project/dataset đã biết (`kltn-text-to-sql`, `mimiciv_3_1_hosp`, `mimiciv_3_1_icu`); location/billing/credentials chưa cấu hình. Cần xác minh 31 bảng và types thật, row counts metadata, IAM, bytes cap thực tế và schema hash. Schema mock không chứa type thật; Mini không còn được dùng.
- **Retrieval:** cần corpus ICD hợp lệ, few-shot index phát hành từ validation-development và kiểm tra trùng đáp án cho internal-check trước khi khóa cấu hình. Không dùng gold test.

## Điểm cần người dùng phê duyệt trước chi phí

1. Project/dataset/location/billing BigQuery, phạm vi quyền MIMIC và mức trần bytes billed/timeout cho pilot validation.
2. Loại schema, dictionary/value evidence, kết quả probe và lỗi SQL nào được phép gửi tới GPT-5-mini; MAC-SQL/SDE-SQL có thể phải gắn nhãn restricted nếu không được phép gửi evidence cần thiết.
3. Model/deployment GPT-5-mini, snapshot nếu có, giới hạn token/calls, bảng giá dùng tính cost và ngân sách API tối đa.
4. Judge CLINSQL chính thức, cấu hình/prompt/version và ngân sách chấm điểm riêng inference.
5. Sau pilot validation, khóa code/prompt/index/config và phê duyệt riêng lượt test chính thức. Chưa có lượt test nào được chạy.
# 14/11/2026 — OpenAI access and research configuration

The ignored `.env` now pins `gpt-5-mini-2025-08-07`, medium reasoning effort,
the US BigQuery datasets, and `SEND_RESULTS_TO_LLM=false`; its key is not
displayed or committed. `run.py` loads allowlisted research variables without
overriding process values. Model retrieval and one nonclinical Responses request
PASS; the paid probe used 13 input and 59 output tokens and is recorded in
`GPT5_MINI_ACCESS_CHECK.md`. The API ledger supports the November-only
unlimited-USD research policy while preserving call/token bounds and a pinned
ledger configuration. **CLINSQL pilot remains 0/5**, with no Phase C.1 BigQuery
approval or aggregate SQL budget yet locked. Phase A approval is not reusable.

The Phase C.1 runner now supports sequential execution of the five pinned cases
with marker-aware resume; it stops on interrupted markers. MAC Selector's
native six-column completion order is covered by a parity test. The selected
CLINSQL/BigQuery/security/mock workflow regression suite has **65/65 PASS**
after these changes; official benchmark and patient SQL remain unrun.
SDE's source three-vote selection rule also has a pure port and synthetic test;
it is not yet connected to a faithful real multi-candidate transport.

The validation-only pre-freeze master manifest is
`data/clinsql/master_experiment_pre_freeze_v1.json` (SHA-256
`fd28d344e6fe0c118a75554abcdb6d631f33b6ebb4e06262c59b6cf71e718173`).
It pins 5 pilot, 152 development and 38 internal-check case IDs from question
text only; the 443 test IDs/hash remain sealed until freeze. An SQLite
`ExperimentState` primitive refuses duplicate claims, altered scope and
pre-freeze test claims, but it is not yet wired to all four real runners.
The selected offline regression suite now has **68/68 PASS**.

# 14/11/2026 — Phase C.1 live pilot, partial

See `GPT5_MINI_LIVE_PILOT_RESULTS.md` for actual request IDs, token usage and
error classification. GPT-5-mini live transport PASS, but no pilot case has a
complete patient-data execution. Version 1 hit native 2048-token incomplete;
version 2 isolated an unknown API outcome and a catalog hallucination;
version 3 routed Guard-rejected SQL into bounded CoT refinement. Its valid
refined SQL dry run estimated 7.91 GiB, exceeding the approved 256 MiB/SQL cap.
No patient SQL executed; SQL ledger remains zero. A wider Phase C.1 BigQuery
budget has been requested and is pending. The versioned markers/logs are
preserved; none is silently rerun or scored. Offline selected suite: 70/70 PASS
after the Guard refinement and budget-estimate logging tests.

# 14/11/2026 — Phase C.2 offline continuation (current state)

The earlier Phase C.1 partial entries above are historical snapshots. The
approved 16 GiB/SQL, 160 GiB aggregate Phase C.1 run subsequently completed
five CLINSQL CoT validation cases with five BigQuery result artifacts. See
`GPT5_MINI_LIVE_PILOT_RESULTS.md` and `PILOT_5_ACCURACY_EVALUATION.md` for the
versioned approvals, audit and diagnostic; do not interpret older 0/5 text as
the current count. The user has **not** approved transferring predicted result
rows to Azure GPT-5-Chat, so official CLINSQL scoring remains unavailable.
Offline native scorer staging parsed 5/5 artifacts; a separate strict result
shape/name diagnostic found 0/5 matches and is not an official score.

SDE-SQL now uses the source-style three-vote judge route, at most three
refinements, and a one-request Chat Completions transport for n=9/n=3. The
transport was tested only with a fake client and has no live runner approval.
The Ours validation-development few-shot corpus has 145 examples and a
runtime-enforced SHA-256 pin; no test gold entered retrieval. The selected
CLINSQL/security/baseline regression suite is **100/100 PASS**. MAC-SQL,
SDE-SQL and Ours still have zero live predictions. No additional OpenAI,
BigQuery or Azure call occurred during this offline continuation.

