# Nhật ký thích nghi baseline

MAC-SQL uses three ChatManager rounds. The first round can invoke Selector,
Decomposer and Refiner because routing is rechecked for each agent in the
group. Later rounds can execute corrections, and the last round can return
an unexecuted correction. The BigQuery adaptations and evidence limits are
documented in [MAC_SQL_FIDELITY_FINAL.md](MAC_SQL_FIDELITY_FINAL.md).

SDE-SQL implements two-stage exploration, native diagnosis, nine-choice
consistency, winner re-execution and the three-choice judge route. The
GoogleSQL, retry and GPT-5-mini adaptations and live blockers are documented
in [SDE_SQL_FIDELITY_FINAL.md](SDE_SQL_FIDELITY_FINAL.md).

**Phase C.2 14/11/2026:** Ours now has a frozen 145-example
development-only few-shot corpus; two development SQLs requiring an absent
`derived` dataset are excluded and recorded. No source/gold/test file changed.

**Phase C.1 live outcome (14/11/2026):** CLINSQL CoT produced five complete
BigQuery predictions across versioned v4/v5 pilot approvals. The v5 SQL budget
raised only the permitted cap to 16 GiB/SQL and 160 GiB aggregate after the
user's scoped approval; it did not change prompt, model, algorithm, schema or
Guard. Two v4 results and three v5 results share model/schema/index/runtime
code fingerprints. The source prompt project-literal adaptation and the
GPT-5-mini output-cap adaptation described below remain material. This is a
successful technical pilot, **not** verified reproduction or a benchmark
score. MAC-SQL/SDE-SQL fidelity gaps remain open.

Không diễn giải code khung là reproduction đã xác nhận. Ghi commit nguồn, thay đổi, lý do, ảnh hưởng thuật toán và phép kiểm chứng trước khi chạy từng baseline.

| Baseline | Trạng thái | Thay đổi đã thực hiện | Lý do | Ảnh hưởng/kiểm chứng |
| --- | --- | --- | --- | --- |
| CLINSQL CoT | Source gốc đã khóa; runner chung chưa tương đương | Adapter đọc trực tiếp `data/splits`; `cot.py` gọi prompt và SQL cleaner từ source gốc; `cot_runner.py` vẫn là khung riêng | Dùng đúng input/prompt và tích hợp protocol chung | 190 validation đọc được, test bị khóa, mock 3 attempts qua test; chưa kiểm chứng model/DB/scorer. Khung thêm dry run và lọc lỗi nên cần so sánh tác động |
| MAC-SQL | Port workflow offline **chưa đủ fidelity để báo điểm** | `clinsql/baselines/mac_sql.py` đọc prompt Selector/Decomposer/Refiner từ source gốc, dùng interface chung, BigQuery SQL, mock value evidence và execution; không sửa source gốc | Kiểm tra luồng agent không gọi API/SQLite | Test mock xác nhận Selector → Decomposer → Refiner và 2 attempts. Chưa tái hiện pruning threshold/column-value sampling/FK formatting và điều phối native đầy đủ; provider giá trị thật cần policy |
| SDE-SQL | Port workflow offline **chưa đủ fidelity để báo điểm** | `clinsql/baselines/sde_sql.py` dùng hai prompt exploration, hàm dựng prompt generation và prompt sửa lỗi/kết quả rỗng gốc (tách AST để không import API code); 2 đợt SQL probes, 9 candidates, nhánh lỗi/nhánh kết quả rỗng; thay riêng SQLite dialect bằng BigQuery; không sửa source gốc | Kiểm tra thứ tự thuật toán với mock | Test mock xác nhận 2 probe stages, 9 candidates, sửa lỗi trực tiếp, probe-based refinement khi rỗng. Phân rã subquery/probe refinement đầy đủ, execution-consistency tie-break và judge_target ba phiếu gốc chưa port tương đương; gold path của source bị loại khỏi runner mới; probe evidence thật chờ policy |

Nguồn: https://github.com/Barryshen1/ClinSQL, https://github.com/wbbeyourself/MAC-SQL, https://github.com/Lancelot-Xie/SDE-SQL.

Đối chiếu chi tiết các nhánh thuật toán và blocker nằm trong [`PAPER_ALGORITHM_AUDIT.md`](PAPER_ALGORITHM_AUDIT.md). Riêng SDE-SQL có đường đọc examples file thiếu trong checkout và nhánh dùng gold trong inference native; port CLINSQL phải loại đường gold khỏi inference và ghi lại thay đổi này trước pilot.

**Gate:** `clinsql.runner` hiện chỉ chấp nhận `MockLLM` và `MockBigQuery`, nên không thể vô tình chạy các port chưa xác minh trên API/BigQuery thật. Trước pilot cần kiểm chứng prompt parity, số lần gọi, logic chọn candidate/judge, dữ liệu probe và thống nhất SQL dialect với source gốc trên tập validation nhỏ. Nếu chính sách không cho phép value evidence/probes, báo biến thể restricted thay vì so điểm như reproduction gốc.

## Phase B — 13/11/2026

- **Chung:** manifest BigQuery 31 bảng `46a816c289178f5b69470fef4cf335f1ff556ad1f4d40b83d600517d76a0ab5d` sinh schema index lexical v1 `89ff2c2f8169c8b65c58821174545231854b374904ebaedd579977973710b318`. `benchmark_backend.py` dựng cùng một `BigQueryAdapter`/guard/allowlist cho bốn method, nhưng execution thật cố ý đóng và không nhận approval Phase A. Index chỉ chứa metadata, không có gold hoặc patient rows. Ours có thể chọn schema context từ index; CLINSQL/MAC/SDE vẫn nhận schema theo prompt hiện hành.
- **CLINSQL CoT:** prompt và hai cơ hội refinement không đổi. Dry run, lọc lỗi và kết quả incomplete là điều kiện bảo vệ bổ sung; vẫn cần đối chiếu hành vi với native BigQuery/model trên pilot validation.
- **MAC-SQL:** Selector → Decomposer → Refiner và bound ba lần chạy không đổi. Kết quả incomplete hiện dừng bằng infrastructure error, không kích hoạt sửa SQL như lỗi model. Native pruning/value sampling/FK formatting chưa đạt parity; mock dùng synthetic value evidence. Nếu chính sách cấm clinical values lên LLM, ghi `adapted/restricted` trước khi đánh giá.
- **SDE-SQL:** hai probe stages, chín candidates và refinement giữ nguyên cấu hình mock. Chọn candidate đã sửa theo `uils.py::find_most_consistent_sql`: nhóm theo tập kết quả (bỏ duplicate), bỏ nhóm rỗng, giữ SQL đầu tiên khi hòa; BigQuery ARRAY/STRUCT được chuẩn hóa thành giá trị so sánh được. Probe/candidate incomplete hiện dừng thay vì dùng dữ liệu thiếu để chọn SQL. Native subquery diagnosis và `judge_target` ba phiếu chưa đạt parity; callback judge trong mock chỉ chứng minh đường điều phối, không tái hiện judge. Chính sách probe evidence cần quyết định trước pilot.
- **Đối chiếu:** `paper_sources.py` PASS trên ba checkout khóa; 2 câu validation công khai × 4 methods chạy mock thành công. Mock SQL/đáp án tổng hợp không phải benchmark score hoặc xác nhận thuật toán tái hiện đầy đủ. Xem `PHASE_B_INTEGRATION_REPORT.md`.

## Phase C.1 — 14/11/2026

- CLINSQL CoT dùng Responses API public transport GPT-5-mini với user-message shape và `max_output_tokens=2048` theo source Azure Responses path; `store=False`, SDK không auto-retry, 31 bảng BigQuery DDL, dry run, redacted error, reader approval và SQL caps là adaptations. Native dùng cache, 50 GB/query và 300 giây; pilot đề xuất 256 MiB và 120 giây để kiểm soát ngân sách. Khi cap censor, không báo model failure hay reproduction tương đương.
- MAC-SQL port `_is_need_prune` theo `avg_column_count<=6 && total_column_count<=30`, giữ các bảng Selector không nhắc và bổ sung join keys khi prune columns. FK hiển thị theo equality thay vì `repr` edges. Value examples và native message history/routing vẫn chưa parity; chưa chạy API.
- SDE-SQL giữ 9-candidate/2-stage probe trong mock. Native subquery diagnosis, fix-probe chain và `judge_target` ba phiếu vẫn thiếu. `OpenAIModelProvider` chặn `n>1` để không đổi semantics/cost của native candidate call một cách âm thầm. Không chạy API/probes thật.
- `BASELINE_FIDELITY_PROGRESS.md` ghi source evidence và giới hạn. Các adaptation này được kiểm tra bằng fake transports, chưa có live parity/score.

## Readiness BigQuery, 12/11/2026

Thay đổi chung cho cả bốn workflow: bỏ nguồn cột/type MIMIC Mini; Schema RAG thật sẽ được dựng lại từ manifest `INFORMATION_SCHEMA` của đúng hai dataset BigQuery và khóa bằng SHA-256. Test offline dùng schema tổng hợp riêng. Đây là thay nguồn metadata/adapter, không thay prompt hay thuật toán cốt lõi của ba paper. Chưa chạy source gốc trên BigQuery; chưa kiểm chứng IAM, SQL dialect thực tế, probe evidence hoặc scorer. Xem `BIGQUERY_READINESS_REPORT.md` và `CLINSQL_RESULT_COMPARISON_POLICY.md`.
# Phase C.1 live adaptations — 14/11/2026

## Phase C.1 version 4: bind source prompt datasets to the verified project

The locked CLINSQL source prompt (`utils/prompt_utils.py`) contains two literal
instructions to use `physionet-data.mimiciv_3_1_hosp` and
`physionet-data.mimiciv_3_1_icu`. The authoritative BigQuery DDL in this
project points instead to `kltn-text-to-sql`. The first real cases repeatedly
generated SQL for the source project despite the correct 31-table DDL; version
3 case Diagnostic Procedures exhausted both native refinements with the same
wrong catalog. Version 4 calls the source prompt builders unchanged, then
replaces **only** those two source project references with the project parsed
from the verified 31-table schema DDL. A parity test proves that no other
prompt text changes. The original source files and gold data remain untouched.
This is a necessary deployment adaptation and is explicitly versioned; it
does not use validation gold or test information.

## Phase C.1 version 3: guarded SQL enters native refinement loop

Version 2 case `Vital_Signs_Monitoring/easy_level_queries/044` produced SQL
referencing `physionet-data` rather than the approved project. The application
SQL Guard rejected it before any BigQuery patient-data job; one OpenAI response
used 3729 input and 2345 output tokens. The earlier runner treated this
`SecurityRejected` as a terminal permission/infrastructure failure, which
prevented CLINSQL's normal SQL-error self-refinement. Version 3 treats only
Guard-rejected model SQL as a sanitized SQL error eligible for the source's
existing two refinement opportunities. IAM denial, bytes cap, timeout and
other infrastructure errors still stop immediately. The Guard, allowlist and
BigQuery limits are unchanged. This is a runner adaptation to a public model
hallucinating a catalog; it is not a prompt tuned from gold answers.

The version-2 first case has an API outcome unknown; its marker and full token
reservation remain untouched. A separate nonclinical long-prompt diagnostic
request succeeded. Version 3 uses a new approval ID, run directory and API
ledger to avoid overwriting either version-2 record. The persistent SQL ledger
is shared, so the approved 3.75 GiB BigQuery aggregate cap cannot reset across
these calibration versions. Version 1/2 are excluded from scoring; their actual
API usage and uncertain reservation are reported as research overhead.

## Phase C.1 version 2: public GPT-5-mini Responses output cap

The locked CLINSQL CoT source sets `max_output_tokens=2048` for its Azure
Responses call. We ran exactly one public OpenAI GPT-5-mini snapshot validation
case at that cap with medium reasoning effort. The API returned `incomplete`:
3729 input tokens, 2048 output tokens including 1536 reasoning tokens, no SQL
execution and USD 0.00502825 estimated inference cost. The case was retained
as a technical calibration run with its original marker/log and is not a
benchmark prediction. No gold or reference was consulted.

For the version-2 pilot, the output cap is increased to 8192 tokens/request and
the timeout to 90 seconds while preserving the source prompt, SQL cleaner,
one-generation/two-refinement algorithm and medium reasoning setting. This is
an endpoint/response-budget adaptation, **not native-equivalent configuration**.
It is versioned by a new API budget SHA-256, approval record and run directory;
the version-1 result is never silently overwritten or scored. The same model
snapshot and reasoning setting remain pinned. Any incomplete response is an
infrastructure/model-generation outcome with usage recorded, not an SQL error.

## Phase C.2 — SDE-SQL source routing and GPT-5-mini transport

The SDE mock runner now follows the source's three-vote `judge_target` route,
one generation pass with `use_check=False`, and up to three refinement steps.
It no longer accepts a Boolean judge callback. A judge-modified SQL is returned
as unexecuted, matching the source boundary; no post-refinement judge call is
added. Source `refine_new.py` is unchanged. Synthetic route tests cover the
three-vote modification and three-correction limit.

The native SDE `connect_gpt` uses one Chat Completions request for nine
candidate choices or three judge votes. A new GPT-5-mini transport preserves
that request count with durable aggregate token accounting and no automatic
retry; it has only fake-client tests. It omits the source's `temperature=0.3`
because the pinned GPT-5-mini model does not accept it, and pins medium
reasoning. This is a disclosed model-compatibility adaptation. SDE has not
run live, its probe evidence policy is unresolved, and the adapter must not
be described as a complete paper reproduction.
