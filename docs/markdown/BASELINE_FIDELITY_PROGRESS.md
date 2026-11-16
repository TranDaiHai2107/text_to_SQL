# Baseline fidelity — Phase C.1, 14/11/2026

**Current outcome 14/11/2026:** CLINSQL CoT technical pilot completed five
BigQuery validation-development cases using the pinned GPT-5-mini snapshot.
This confirms the adapted generation → SQL Guard/dry run → optional native
self-refinement → execution → restricted-artifact path, but **does not**
establish SQL Score, Execution Score or parity with the original paper.
MAC-SQL and SDE-SQL remain offline mock workflows with the fidelity gaps below.
See `GPT5_MINI_LIVE_PILOT_RESULTS.md`; earlier no-live-run statements below
are historical.

**Transport update, 14/11/2026:** GPT-5-mini snapshot access and a nonclinical
Responses request PASS (see `GPT5_MINI_ACCESS_CHECK.md`). The current Phase C.1
API draft retains the source's 2048 output tokens/request and pins medium
reasoning effort explicitly for all methods. No baseline clinical
inference or BigQuery benchmark execution has yet run.

Đối chiếu source khóa bởi `PAPER_SOURCE_LOCK.json`; `python paper_sources.py` PASS. Không chỉnh bất kỳ file nào dưới `external/`. **Không baseline nào được tuyên bố full reproduction trên GPT-5-mini/BigQuery thật.** Chỉ CLINSQL CoT có đường runner pilot chuẩn bị để gọi model thật, nhưng chưa chạy request nào.

## CLINSQL CoT + Self-Refinement

Live pilot adaptation: public GPT-5-mini with medium reasoning used all 2048
source output tokens and returned `incomplete` on the first case. The version-2
profile raises the cap to 8192 and is explicitly **adapted**, while preserving
the source prompt and at most two SQL-error refinements. Version 3 adds a
sanitized refinement for model SQL rejected by the application table guard;
the guard remains active. A refined SQL passed the guard but exceeded the
approved BigQuery bytes cap at dry run, so fidelity/score parity is still
unverified. See `GPT5_MINI_LIVE_PILOT_RESULTS.md`.

Nguồn: `external/clinsql_official/model_inference/clinical_sql_benchmark_evaluator_CoT.py` và `utils/prompt_utils.py`, `utils/sql_utils.py`. `src/ehrqa/clinsql/cot.py` gọi prompt builder và cleaner từ đúng checkout này. Runner giữ một generation và tối đa hai refinement **chỉ sau lỗi SQL**, không thêm attempts. `openai_provider.py` gửi đúng một user message theo shape Responses API của source (dòng 140–169), khóa 2048 output tokens, không thêm system message, không tự đặt temperature. `store=False`, SDK `max_retries=0`, read-only SQL Guard, dry run, redacted error, timeout/bytes/output caps là adaptations vận hành. Native CLINSQL dùng Azure Responses deployment, cache query, cap 50 GB và timeout 300 giây; pilot dùng OpenAI public endpoint và đề xuất 256 MiB/120 giây. Phải ghi rõ mọi case bị censor do cap; không chấm thành lỗi SQL của model. API account/model access và native-versus-adapted score parity chưa kiểm chứng.

## MAC-SQL

Update 14/11: Selector's six-column completion now follows the native ordering:
selected/key columns in source order, then the earliest omitted columns appended
until six. A synthetic parity test checks this order. Native column-value
sampling and ChatManager routing remain unresolved, so this is still an adapted
mock workflow rather than a benchmark-ready reproduction.

Nguồn: `external/mac_sql_official/core/agents.py` (Selector `_is_need_prune`, `_get_db_desc_str`, Decomposer, Refiner) và `core/chat_manager.py`. Phase C.1 đã port quy tắc Selector chỉ prune khi **không đồng thời** `avg_column_count<=6` và `total_column_count<=30`; unmentioned tables được giữ như native, selected columns giữ declared JOIN keys và tối thiểu sáu cột khi phù hợp. FK text nay là từng equality thay vì Python `repr` của edge list. Test parity tổng hợp kiểm tra threshold và giữ bảng không được nhắc. Selector → Decomposer → Refiner cùng ba lần thực thi tối đa vẫn chạy mock.

**Còn khác:** native lấy value examples trực tiếp từ SQLite và dựng BIRD schema description với column descriptions/values; adapter chỉ có BigQuery metadata và callback value evidence tổng hợp. Declared domain JOIN edges không đồng nhất foreign-key inventory của SQLite gốc. `ChatManager` message history/routing, native `drop_all`/column ordering trong mọi trường hợp và xử lý timeout/error chưa được port đầy đủ. Không gửi patient/clinical values lên LLM khi chưa có data policy; không chạy MAC trên API thật và không gắn nhãn reproduction nếu phải bỏ evidence.

## SDE-SQL

Update 14/11: `sde_judge.py` ports the source's three-vote decision rule as a
pure component: at least two `Modification="True"` votes select the last
modified SQL. A synthetic parity test PASS. This is not wired into a real SDE
run because the current Responses transport intentionally refuses `n=3` and
`n=9`; separate-request adaptation, durable per-candidate checkpoints and
subquery diagnosis must be completed and disclosed first.

Nguồn: `external/sde_sql_official/src/explore_new.py`, `src/refine_new.py` (đặc biệt `probe_refine_sql`, `judge_target`) và `src/uils.py::find_most_consistent_sql`. Hai tầng exploration/probes, 9 candidates, result-set majority bỏ kết quả rỗng và tie-break theo candidate đầu tiên đã chạy mock. BigQuery ARRAY/STRUCT được chuẩn hóa để grouping, không ghi raw result vào log. Source `judge_target` lấy ba phiếu khi self-consistency bật; adapter hiện chỉ có callback judge boolean. Native `get_subsqls`/`generate_result` phân rã subquery và chuỗi diagnosis probe → fix probes → empty-result prompt; adapter hiện có một vòng refine probes, chưa tương đương. Prompt/model routing và evidence policy chưa khóa; `OpenAIModelProvider.generate(n=9)` cố ý fail closed vì chuyển một native 9-candidate call thành chín requests riêng sẽ thay semantics/cost. Gold path trong native source không vào adapter CLINSQL inference. **SDE chưa đủ fidelity để pilot hoặc so điểm như reproduction**.

## Thử nghiệm parity và adaptation bắt buộc

`tests/test_phase_c1_pilot.py` kiểm tra MAC threshold, source prompt serialization của CLINSQL, CoT fake API→SQLGlot→fake BigQuery, checkpoint/typed result và budget. `tests/test_phase_b_integration.py` kiểm tra SDE candidate majority/tie-break và mock E2E bốn workflows. Các test này chỉ có giá trị về thuật toán/đường chạy tổng hợp; chưa xác nhận output SQL/score trên dữ liệu thật. BigQuery dialect, service-account gate, redacted errors và loại gold path là adaptations bắt buộc, đã/đang ghi tại `BASELINE_ADAPTATION.md`. Mọi thay đổi còn lại cần test parity với source gốc trước khi mở MAC/SDE paid pilot.
