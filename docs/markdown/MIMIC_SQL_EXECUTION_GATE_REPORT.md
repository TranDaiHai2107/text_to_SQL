# Gate trước MIMIC-IV SQL smoke — 13/11/2026

**Trạng thái: CHƯA MỞ execution.** Không chạy thêm SQL trên dữ liệu MIMIC, không đổi IAM, không gọi OpenAI/judge/benchmark. ADC vẫn impersonate `kltn-sql-reader@kltn-text-to-sql.iam.gserviceaccount.com`.

## Blocker IAM thực sự

- Bằng chứng hiện có: Owner xác nhận service account chỉ có project role trực tiếp `roles/bigquery.jobUser`; HOSP và ICU cấp Data Viewer. Dataset metadata hiện có direct `READER` entries. Trên 31/31 bảng, `testIamPermissions` trả `get/getData`, không trả `update/updateData/delete`. Metadata preflight và 5 dry runs PASS; `SELECT 1` đã PASS với 0 bytes billed.
- **Chưa thể xác minh:** project thuộc Folder/Organization nào, các IAM bindings/conditions/deny policies ở những ancestor đó, và quyền có thể kế thừa qua group. Cloud Resource Manager `projects.get` v1 và v3 đều trả **403** dưới service account. `projects.getIamPolicy` cũng trả 403. Owner đã chạy Policy Troubleshooter nhưng Outcome=`Unknown` do thiếu quyền xem toàn bộ Organization/Folder policy. Kết quả âm tính của `testIamPermissions` không thay thế được kiểm tra này. Vì vậy IAM là **`READ_ONLY_LIKELY`**, chưa phải `VERIFIED_READ_ONLY`.
- Cách giải quyết không đổi quyền: Owner đọc project parent bằng `gcloud projects describe kltn-text-to-sql --format='json(projectId,parent)'` và gửi **chỉ** parent ID/type; người đang có quyền quản trị ở Folder/Organization kiểm tra effective IAM/conditions/deny policy cho service account trên hai datasets. Nếu Owner vẫn không nhìn thấy policy ancestor, cần administrator hiện có thực hiện kiểm tra; không cấp thêm quyền chỉ để chạy thử. Không gửi credentials.

## Result artifacts và logs

- Tạo `results/restricted` trong workspace và vô hiệu hóa ACL inheritance. Verifier Windows trả `safe=true`, current user FullControl, 0 ACL rules ngoài current user/SYSTEM/Administrators. Default `ResultArtifactStore` dùng verifier này và từ chối ghi khi ACL không đạt.
- Một artifact **tổng hợp** đã round-trip qua store và được xóa; không lưu dữ liệu MIMIC. `MeteredDatabase` nay từ chối `capture_rows=True` đối với database không phải synthetic mock. Logs mặc định chỉ giữ SQL, column metadata, job ID, bytes, latency/status, không raw rows.
- Trước khi lưu kết quả MIMIC thật, cần xác nhận nơi lưu/retention theo điều kiện sử dụng MIMIC; ACL cục bộ PASS không tự thay cho quyết định dữ liệu.

## Bốn SQL đang chờ quyết định

Đã dry run PASS; SQL đầy đủ và reference nằm trong `BIGQUERY_SQL_EXECUTION_PREP_REPORT.md`. Giữ timeout **30 giây**, cap đã đề xuất và giới hạn output một hàng cho smoke:

- `hosp_patients_count`: cap **10 MiB**, dry run 0 bytes.
- `icu_icustays_count`: cap **10 MiB**, dry run 0 bytes.
- `icu_hosp_join`: cap **20 MiB**, dry run 5,123,888 bytes.
- `clinsql_validation_043`: cap **23 MiB** (24,117,248 bytes), dry run 20,032,585 bytes; chỉ đổi project prefix trong SQL chạy, không sửa gold source.

## Hai đường mở gate

1. **Xác minh IAM:** administrator có quyền xem đủ project/folder/organization xác nhận không có `bigquery.tables.update`, `updateData`, `delete` hoặc role ghi kế thừa/qua group trên HOSP và ICU; lưu bằng chứng và đánh dấu `VERIFIED_READ_ONLY`. Sau đó người dùng phê duyệt chính xác bốn SQL/cap trên trước execution.
2. **Nếu Organization/Folder không thể kiểm chứng:** người dùng có thể đưa **quyết định chấp nhận rủi ro riêng bằng văn bản**, nêu principal `kltn-sql-reader`, phần IAM chưa biết, đúng bốn SQL IDs, caps/timeout/output limit ở trên, nơi lưu kết quả/retention và phạm vi thời gian. Quyết định này không đổi trạng thái thành `VERIFIED_READ_ONLY` và không mở execution chung; chỉ cho phép các SQL được liệt kê nếu người dùng phê duyệt. **Chưa có quyết định như vậy.**

Offline tests liên quan CLINSQL/BigQuery/security/result handling: **43 PASS**. Legacy tests tiếng Việt/PostgreSQL không sửa. Không triển khai migration tiếng Việt.
