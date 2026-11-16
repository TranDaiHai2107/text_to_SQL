# Phase B — CLINSQL/BigQuery end-to-end integration (offline)

Ngày 13/11/2026. **Trạng thái: hạ tầng mock end-to-end PASS; pilot GPT-5-mini thật chưa được mở.** Không gọi OpenAI API, CLINSQL judge hoặc BigQuery trong Phase B. Không chạy benchmark test, không sửa ứng dụng tiếng Việt, gold SQL, reference results hay source gốc các paper.

## Những phần đã tích hợp

| Hạng mục | Kết quả và bằng chứng |
| --- | --- |
| Schema authoritative | Đọc manifest `data/schema/manifests/mimiciv_3_1_20261112T143303Z.json`, 31 bảng (22 HOSP, 9 ICU), SHA-256 `46a816c289178f5b69470fef4cf335f1ff556ad1f4d40b83d600517d76a0ab5d`. Không đọc MIMIC Mini. |
| Schema RAG index | `schema_index.py` dựng/lưu/kiểm tra index lexical v1 từ metadata thật tại `data/schema/indexes/schema_lexical_v1_46a816c289178f5b.json`; index SHA-256 `89ff2c2f8169c8b65c58821174545231854b374904ebaedd579977973710b318`. Ours dùng index để chọn bảng, sau đó khép JOIN bằng quan hệ đã khai báo. Index đổi khác manifest sẽ fail closed. Index không chứa gold, reference hay dữ liệu bệnh nhân. |
| Shared executor | `benchmark_backend.py` tạo `BigQueryAdapter` cùng manifest, table allowlist và BigQuery config cho cả bốn methods. `SmokeExecutionConfig` giữ profile Phase A; `BenchmarkExecutionConfig` có bytes/timeout/row cap riêng. Backend benchmark chỉ dry-run; không nhận approval Phase A và `allow_data_execution=False` ở adapter lẫn client. Reader ADC được kiểm tra ở transport khi có approval hợp lệ mới. |
| Result handling | `BigQueryClient` chuyển tên/kiểu cột và báo `total_rows`; adapter đánh dấu `complete=False` nếu page thiếu hàng. Official staging từ chối incomplete result. `ResultArtifactStore` v2 giữ thứ tự, duplicate, NULL, DATE, TIMESTAMP, NUMERIC, ARRAY, STRUCT, BYTES và float đặc biệt; v1 scalar artifact Phase A vẫn đọc được. Kết quả thật chỉ được lưu dưới ACL hạn chế; application log không giữ raw rows. Saved prediction chỉ ghép protected artifact khi SHA-256, SQL, job ID và row count khớp log, không gọi LLM. |
| Budget/resume | `PersistentSQLBudgetLedger` dùng SQLite transaction để reserve toàn bộ bytes cap trước query, reconcile actual billed, giữ nguyên reservation chưa biết billing sau crash; giới hạn calls/probes/bytes theo câu và experiment. Runner tạo `.started` marker độc quyền trước model call, lưu fingerprint của câu/model/schema và chỉ resume từ prediction đã lưu. Marker còn mà log thiếu phải kiểm tra thủ công, không tự gọi lại API. |
| Logging/latency | Log hiện giữ SQL, cột/kiểu, row count, job ID, bytes, status, LLM calls/tokens và thời gian monotonic tổng pipeline. `MeteredDatabase` chỉ cho phép lưu rows khi `is_synthetic_mock=True`; lỗi database được lọc khỏi log. Điều kiện incomplete ở MAC/SDE dừng như lỗi hạ tầng, không được đếm là lỗi SQL của model. |

## Mock end-to-end và regression

- `tests/test_phase_b_integration.py`: **9 PASS**. Hai câu hỏi tiếng Anh đọc trực tiếp từ 190 câu validation CLINSQL công khai; mỗi câu chạy **4 workflows** với `MockLLM` và `MockBigQuery`, tổng 8 predictions/checkpoints. SQL/result trong mock là tổng hợp, không lấy gold; đây là kiểm tra điều phối, **không phải điểm benchmark hoặc kiểm tra độ đúng lâm sàng**.
- Các test mới kiểm tra index/hash và tamper detection, persistent budget qua restart, artifact typed multi-row/duplicate, replay offline, incomplete paging, benchmark execution gate và SDE consistency tie-break.
- Bộ regression được chọn: **62 PASS / 62** với `python -m pytest tests/test_phase_b_integration.py tests/test_controlled_execution.py tests/test_bigquery_execution_prep.py tests/test_clinsql_foundation.py tests/test_clinsql_offline_workflows.py tests/test_agentic_evidence.py tests/test_agentic_selection.py -q --basetemp .pytest_phase_b_final3` (`PYTHONPATH=src`). Đây không phải toàn bộ legacy suite; các test ứng dụng tiếng Việt/PostgreSQL chưa được xử lý theo phạm vi người dùng.
- `python paper_sources.py` **PASS**: ba checkout đúng commits/hashes khóa trong `PAPER_SOURCE_LOCK.json`; không chỉnh source gốc.

## Fidelity và giới hạn nghiên cứu

| Method | Đã kiểm tra offline | Khoảng thiếu trước khi công bố reproduction |
| --- | --- | --- |
| CLINSQL CoT + Self-Refinement | Prompt/SQL cleaner từ checkout gốc; tối đa hai lượt sửa khi lỗi; mock dùng chung schema/DB interface. | Cần đối chiếu model transport, BigQuery live và output official scorer. Dry run và lỗi đã redacted là adaptation có ảnh hưởng tiềm năng. |
| MAC-SQL | Selector → Decomposer → Refiner, ba vòng tối đa, source prompt templates, mock value evidence. | Native pruning threshold, lấy column values, FK formatting và message routing chưa đạt parity. Clinical value evidence thật chưa được phê duyệt truyền tới LLM; không gọi bản này là native reproduction. |
| SDE-SQL | Hai lượt exploration/probe, chín candidates, hai nhánh refinement; candidate selection đã khớp quy tắc result-set majority, bỏ empty và giữ ứng viên đầu tiên khi hòa trong source `uils.py`. | Native phân rã/diagnosis subquery và `judge_target` ba phiếu chưa tương đương. Probe evidence thật và policy LLM chưa được quyết định; callback mock không chứng minh judge fidelity. |
| Ours | Schema RAG từ index metadata thật, ICD/few-shot interfaces, SQL generation/validation và agentic correction chạy mock. | Cần pilot live để kiểm tra retrieval quality, execution budget, candidate selection và evaluator; không dùng test gold trong inference. |

SDE hoặc MAC nếu phải bỏ evidence vì chính sách dữ liệu sẽ được ghi `adapted/restricted`, không so sánh dưới nhãn reproduction nguyên bản. Chưa chỉnh algorithm để giảm calls hay làm baseline yếu đi. Chi tiết adaptation ở `BASELINE_ADAPTATION.md` và source audit ở `PAPER_ALGORITHM_AUDIT.md`.

## Execution Score và cost fairness

- Row cap/timeout/bytes cap **không được biến thành Execution Score thấp**: `complete=False`, timeout, permission hoặc budget failure phải được báo `infrastructure_censored`/excluded theo protocol đã khóa, kiểm tra nguyên nhân và chỉ đánh giá lại sau approval phù hợp. Không gửi partial result vào official evaluator. Cần thống nhất maximum output size/timeout theo validation để không ưu ái method nào; SDE SQL probes được tính trong cùng ledger và báo riêng calls/probes/bytes.
- `prepare_saved_run_sample` có thể stage artifact đã lưu; official CLINSQL scorer/judge chưa chạy và không bị sửa. Việc in ARRAY/STRUCT ra CSV theo định dạng mà official evaluator mong đợi vẫn cần test bằng dữ liệu được phê duyệt trước khi chấm thật.
- Phase A JOIN có khoảng chờ CLI/tool khoảng **983 giây**, trong khi client query/result **2.218 giây** và server execution **0.401 giây**; không có bằng chứng job bị tạo lại. Nguyên nhân client/tool/auth scheduling chưa xác định offline. E2E latency pilot sẽ đo từ lúc runner nhận câu tới checkpoint cuối bằng monotonic clock, tách model latency, BigQuery client latency, server job latency, setup/CLI overhead và evaluation latency. Không dùng riêng server job time làm latency tổng.

## Điều kiện trước pilot GPT-5-mini trên 5–10 validation questions

**Chưa sẵn sàng mở pilot có phí.** Cần triển khai/kiểm chứng model transport thật và benchmark-scoped approval riêng, sau đó đóng băng config và chạy thử chỉ khi người phụ trách phê duyệt. Phase A approval tuyệt đối không hợp lệ cho benchmark SQL.

Các quyết định người phụ trách cần xác nhận trước pilot: GPT-5-mini model snapshot/API/settings dùng chung; giới hạn tổng USD, tokens, calls, SQL bytes/probes theo method và toàn pilot; timeout và max result rows/bytes sao cho không censor Execution Score; chính sách lưu artifact và retention; liệu metadata, lỗi redacted, MAC column values, SDE probe labels/results và judge input nào được gửi lên LLM; số câu validation và khóa split/retrieval index; policy xử lý infrastructure-censored cases. Cần xác minh protected result storage/ACL tại thời điểm chạy. Không dùng gold SQL, reference CSV hoặc rubric test trong inference.

## File Phase B đã thêm/sửa

Thêm `src/ehrqa/clinsql/schema_index.py`, `src/ehrqa/clinsql/benchmark_backend.py`, `data/schema/indexes/schema_lexical_v1_46a816c289178f5b.json`, `tests/test_phase_b_integration.py`, báo cáo này. Sửa `src/ehrqa/clinsql/proposed.py`, `runner.py`, `execution_budget.py`, `result_artifacts.py`, `bigquery_client.py`, `bigquery_adapter.py`, `baselines/mac_sql.py`, `baselines/sde_sql.py`, `evaluator.py` và `BASELINE_ADAPTATION.md`. Các thay đổi Phase A có sẵn trong working tree được giữ nguyên.
