# Controlled BigQuery execution — 13/11/2026

**Cập nhật sau báo cáo chuẩn bị:** bốn SQL Phase A đã thực thi và PASS 4/4. Xem `PHASE_A_EXECUTION_RESULTS.md`. Các dòng trạng thái "execution đóng" bên dưới mô tả thời điểm trước khi người dùng phê duyệt scoped risk acceptance.

**Kết luận: hạ tầng Phase A đã được dựng và kiểm thử offline; execution trên MIMIC-IV vẫn ĐÓNG.** Không có patient-data SQL, OpenAI API, CLINSQL judge hoặc benchmark job nào được chạy trong lượt này. Bốn SQL đã dry run PASS ở đợt trước; lượt này chỉ kiểm tra parser bằng fake client và giữ nguyên caps.

## IAM và ADC

- **ADC principal: PASS.** Kiểm tra lại bằng Python của `.venv_papers/clinsql`: credential type `google.auth.impersonated_credentials.Credentials`, target chính xác `kltn-sql-reader@kltn-text-to-sql.iam.gserviceaccount.com`; `GOOGLE_APPLICATION_CREDENTIALS` không đặt. Không in token hoặc credential contents.
- **Quyền đọc bảng: PASS theo bằng chứng đã có.** Project role trực tiếp `roles/bigquery.jobUser`; hai datasets cấp Data Viewer; 31/31 `testIamPermissions` trả get/getData và không trả update/updateData/delete. Metadata 31/31, 5/5 dry run và constant SQL đã PASS trước đó.
- **Read-only IAM: `READ_ONLY_LIKELY`, chưa `VERIFIED_READ_ONLY`.** Service account không đọc được project hierarchy/IAM policy (403); Policy Troubleshooter do Owner chạy trả `Unknown` vì thiếu Organization/Folder policy. Quyền kế thừa, group bindings và policy cấp cao chưa được chứng nhận. Không thay đổi IAM. Application gate không chứng minh service account không có quyền ghi ở IAM.
- **Điều kiện rủi ro:** `READ_ONLY_LIKELY_WITH_APPROVED_RISK` chỉ là *trạng thái quyết định có phạm vi*, không đổi nhãn IAM thành verified. Người có thẩm quyền phải xác nhận không trái Organization policy bắt buộc và quyết định riêng về lưu trữ/retention trước khi hoàn tất approval record. Mọi `PERMISSION_DENIED` thực tế từ BigQuery vẫn dừng job.

## Lớp bảo vệ đã triển khai

1. `BigQueryAdapter` parse đúng một câu SELECT/CTE bằng SQLGlot dialect BigQuery; chặn mutation, nhiều statements, external access, qualified user-defined/remote routines và table ngoài manifest. CTE hợp lệ hiện được chấp nhận; bảng thật trong CTE vẫn phải thuộc 31 bảng ở hai datasets. Nếu không có manifest, table query bị từ chối.
2. `BigQueryClient.execute` cần đồng thời bật execution, có manifest đã xác minh, approval có thời hạn và case ID, ADC **và chính credentials của SDK client** đều impersonate đúng reader, SQL hash chính xác, scope project/datasets/location và caps. Cờ `allow_data_execution=True` đơn lẻ không còn mở query job. Approval hiện chỉ hỗ trợ `phase_a_smoke`; các phase sau không thể dùng lại hồ sơ này.
3. `docs/PHASE_A_APPROVAL_DRAFT.json` được tạo từ đúng bốn SQL nguồn và manifest. Hash/cap của bốn SQL cũng được khóa trong gate; sửa JSON thành SQL khác không mở execution. Đây là **bản nháp không thực thi được**: approver, authority, policy/storage references và thời hạn còn trống, risk acceptance là `false`. `ExecutionApproval.from_file` từ chối bản nháp. Hồ sơ hoàn tất phải được đặt trong thư mục ACL protected; marker và summary lưu SHA-256 của hồ sơ. Không có approval đã hoàn tất.
4. `bigquery-approved-smoke` mặc định `PLAN_ONLY` và không load ADC. Sau này, chỉ `--execute-approved` kèm hồ sơ hợp lệ trong `results/restricted` mới có thể chạy một case; case cần dry run trước, cap 10/10/20/23 MiB, timeout 30 giây. Adapter trả tối đa một row; nội bộ fetch tối đa hai row để phát hiện truncation. Marker `phase_a_<case_id>.started` được tạo độc quyền trước query, chặn cả khi approval ID thay đổi. Query cache reuse tắt; đúng một scalar mới được lưu.
5. BigQuery job vẫn có `maximum_bytes_billed`, result timeout và cancellation khi `result()` lỗi. `SQLBudgetLedger` và `BudgetedDatabase` có thể giới hạn SQL calls, probes, bytes/question và bytes/experiment trong **một process**, bảo lưu full per-query cap trước job; vượt trần thì dừng. Chưa có durable multi-process ledger hoặc integration vào batch runner, nên không coi đây là full-benchmark budget enforcement.
6. Result rows được tách vào `ResultArtifactStore` có Windows ACL verifier; application log chỉ ghi SQL, schema output, job ID, bytes, latency, status và lỗi đã redacted. `MeteredDatabase` từ chối raw rows logging đối với database thật. ACL `results/restricted` kiểm tra lại: `safe=true`, inheritance disabled, zero unexpected ACL rules. Chưa lưu result MIMIC thật; retention/policy chưa được phê duyệt.

SQL Guard là lớp bảo vệ ứng dụng; IAM tối thiểu và BigQuery job limits vẫn bắt buộc. Không có cơ chế nào tự bỏ guard khi SQL bị từ chối hoặc tự tăng bytes cap. Source ba paper và gold SQL chính thức không thay đổi.

## Kiểm thử và file thay đổi

- **50 offline tests PASS** sau bổ sung kiểm tra marker một case qua nhiều approval ID, result một scalar và query cache flag. Các test trước đó bao gồm approval scope/expiry, khóa hash từ source validation, budget calls/probes/bytes, rejected SQL, CTE, manifest allowlist, principal mismatch giữa ADC và SDK client, transport timeout/cancel, permission denied, bytes cap, result serialization/log redaction, CLINSQL mock và agentic security. Parser cũng chấp nhận cả năm smoke SQL bằng fake client và manifest thật, không gọi BigQuery.
- ADC recheck PASS. Windows ACL verifier PASS khi chạy read-only ngoài sandbox. Không chạy lại BigQuery metadata/dry-run vì bằng chứng trước vẫn được giữ; không có query job mới trong lượt này.
- Code mới: `src/ehrqa/clinsql/execution_control.py`, `execution_budget.py`, `src/ehrqa/cli/bigquery_approved_smoke.py`, `scripts/build_phase_a_approval_draft.py`, `tests/test_controlled_execution.py`, `docs/PHASE_A_APPROVAL_DRAFT.json`.
- Code sửa: `src/ehrqa/clinsql/bigquery_client.py`, `bigquery_adapter.py`, `src/ehrqa/cli/bigquery_sql_smoke.py`, `src/ehrqa/text2sql/logging.py`, `run.py` và các tests BigQuery liên quan. Không sửa code dưới `external/` hoặc ứng dụng tiếng Việt.

## Gate để mở Phase A

1. Người phê duyệt có thẩm quyền cung cấp quyết định riêng: xác nhận principal, bốn case IDs, 10/10/20/23 MiB, timeout 30 giây, output một row, khoảng thời gian hiệu lực, IAM risk còn lại và sự phù hợp với Organization policy bắt buộc. Nếu có bằng chứng IAM ancestor đầy đủ, dùng `VERIFIED_READ_ONLY`; nếu không, giữ `READ_ONLY_LIKELY_WITH_APPROVED_RISK` với chấp nhận rủi ro rõ ràng. App chỉ kiểm tra cấu trúc/scope hồ sơ, **không tự xác thực thẩm quyền của người ký**.
2. Chốt nơi lưu result artifacts và retention theo điều kiện sử dụng MIMIC-IV; điền reference vào approval. ACL cục bộ PASS nhưng chưa thay thế policy dữ liệu.
3. Trước lúc chạy, recheck ADC, manifest hash, SQL hash, dry run và caps; nếu phát hiện quyền ghi bất ngờ, credential khác, manifest khác, lỗi IAM thực tế hoặc policy conflict, dừng.
4. Thực thi từng case bằng `bigquery-approved-smoke --execute-approved` sau khi các điều kiện trên được đáp ứng. Bản nháp hiện tại không cho phép execution. Không tự chuyển sang Phase B/C.

Chi tiết bốn SQL và ước tính dry run nằm trong `BIGQUERY_SQL_EXECUTION_PREP_REPORT.md`. Checklist để phê duyệt Phase A: `PHASE_A_EXECUTION_APPROVAL_CHECKLIST.md`. Xem `FULL_BENCHMARK_EXECUTION_PLAN.md` cho readiness bốn phương pháp và các phase sau.
