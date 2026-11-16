# Research validity regression — sau Phase A, 13/11/2026

**Kết luận:** Phase A chỉ thay execution infrastructure và diagnostic guards; không thay prompt, model, retrieval, candidate/probe counts, refinement logic, gold/reference/rubric hay official CLINSQL scorer. **53 selected offline tests PASS**; full legacy suite tiếng Việt/PostgreSQL vẫn có collection issues đã biết và không được sửa/xóa để tạo PASS giả. Không có model inference hoặc judge call trong Phase A.

## Trước và sau execution gate

- Trước: transport mặc định tắt patient-data execution; chỉ constant smoke được phê duyệt riêng; IAM `READ_ONLY_LIKELY` khiến bốn SQL MIMIC bị chặn.
- Sau: `READ_ONLY_LIKELY_WITH_APPROVED_RISK` chỉ hoạt động khi approval đúng reader principal, US/project/datasets, manifest hash, exact SQL hashes, thời hạn và caps. `organization_policy_clearance_reference` có thể để trống ở risk mode, nên không tuyên bố phê duyệt Organization. Mọi `PERMISSION_DENIED` thực tế vẫn dừng. Approval Phase A không cho SQL ngoài bốn case và không mở benchmark runner.
- SQL Guard vẫn parse BigQuery SELECT/CTE, allowlist 31 bảng và chặn DDL/DML, scripts/multi-statement, external/remote access. Dry run, bytes cap, timeout, cancellation, marker và ACL được giữ. Test với DDL/DML/remote/UDF/out-of-scope tables PASS; cả bốn SELECT smoke được parser chấp nhận trước execution.

## Bảo toàn thuật toán và nguồn

`paper_sources.py` sau Phase A xác nhận commit/key files: CLINSQL `1d819960eb3ce3ac0e9beb4e801810a05735fd58`, MAC-SQL `31a9df5e0d520be4769be57a4b9022e5e34a14f4`, SDE-SQL `e425408fcb13d69b0bd15f917b819591805a8973`. 190 validation và 443 test vẫn được kiểm kê. Không sửa checkout dưới `external/`.

Các module inference/workflow sau giữ nguyên SHA-256 trong suốt thay đổi gate lần này:

- CLINSQL prompt/cleaner `cot.py`: `5d4667107cd306b494345246bf16878186cb0797afa9ec2197dfa89b212fc74b`; CoT workflow `cot_runner.py`: `2824c0efd7fefd89f7b8ad9ef81c620772bebaa3c46ac29255d6f77895456bb9`.
- MAC-SQL workflow: `a7226a8617e4bf53e3f0c9af3c459eb33c57e384ab5354d7fa7607ab846b35f1`; SDE-SQL workflow: `8583fbad5eddf730c4e21da2b3e35519a6e1da89f48d1fc483555e53bcda6452`.
- Proposed pipeline `proposed.py`: `1d247efd6ba689c7f09d51a6ae7550007d6aac595d386e863e22aadb4c3fba58`; offline runner `runner.py`: `f07a4dafe043e4415de0b1073203d4643f3b731a0d31d4c4227f0b100b4a6217`.

Mock regression tests xác nhận MAC-SQL giữ Selector → Decomposer → Refiner; SDE-SQL giữ hai probe stages và chín candidates; CLINSQL CoT giữ tối đa hai cơ hội refinement; proposed mock generation/validation/correction vẫn chạy. Không có thay đổi model ID, sampling config hoặc số lần gọi để vượt budget. Các fidelity gaps đã ghi trong `BASELINE_ADAPTATION.md` vẫn còn; kết nối BigQuery không chứng minh reproduction.

## Failure accounting và result completeness

- `execution_errors.py` chuẩn bị mapping riêng cho `SQL_SYNTAX_ERROR`/`SQL_EXECUTION_ERROR`, `BUDGET_EXCEEDED`, `TIMEOUT`, `PERMISSION_DENIED`, `SECURITY_REJECTED` và `INFRASTRUCTURE_ERROR`; Phase A runner ghi `COMPLETE` hoặc `TRUNCATED_RESULT`/lỗi khi cần. BigQuery SDK Forbidden/Unauthorized, DeadlineExceeded, service errors và bytes-cap BadRequest được map sang lỗi không phải SQL; error text ra log được redacted. Hạ tầng không bị gộp thành model SQL failure trong BigQuery adapter. Unit test kiểm tra các nhánh bằng fake SDK errors. Việc nối cùng taxonomy vào toàn bộ benchmark runner vẫn là việc Phase B.
- `SmokeExecutionConfig` khóa một row cho Phase A. `BenchmarkExecutionConfig` từ chối row cap = 1 và vẫn tắt data execution cho tới khi có approval riêng. `BigQueryAdapter` đặt `Execution.complete=False` khi thấy thêm row sentinel. `prepare_official_sample` trong **local staging** nay từ chối result chưa đầy đủ; official source scorer dưới `external/` không đổi. Không chấm result bị truncate thành result hợp lệ.
- Phase A runner xác nhận đúng một scalar và lưu failure status riêng nếu một job bị lỗi; marker vẫn còn để tránh retry âm thầm. Bốn lượt thật đều `COMPLETE`, không có failure/truncation.

## Kiểm thử đã chạy và giới hạn kết luận

Lệnh: `python -m pytest tests/test_controlled_execution.py tests/test_bigquery_execution_prep.py tests/test_clinsql_foundation.py tests/test_clinsql_offline_workflows.py tests/test_agentic_evidence.py tests/test_agentic_selection.py -q` → **53 PASS**. `paper_sources.py` PASS. ACL verifier và retention plan `NOT_DUE` cho 4/4. Có một khoảng chờ client/tool bất thường ở JOIN, nhưng job ghi latency 2.218 giây; cần điều tra trước khi dùng latency end-to-end làm metric hiệu quả.

**Chưa chứng minh:** output SQL của một model trả phí trước/sau (không gọi model); MAC-SQL/SDE-SQL full fidelity; BigQuery benchmark mode nhiều hàng trên dữ liệu thật; official CLINSQL judge/evaluator parity; handling budget và resume ở batch; data policy cho probe evidence; evaluation denominator khi có infrastructure failures. Các trạng thái này phải được khóa trong protocol Phase B/C, không âm thầm loại case hoặc cho 0 điểm theo lỗi hạ tầng.
