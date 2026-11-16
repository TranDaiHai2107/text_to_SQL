# BigQuery SQL Execution Preparation — updated 13/11/2026

**Gate update 13/11:** Project hierarchy metadata API v1/v3 và project IAM policy đều trả 403 dưới service account; ancestor IAM chưa kiểm chứng. Windows ACL cho `results/restricted` đã kiểm tra PASS, artifact tổng hợp round-trip rồi xóa; `capture_rows=True` bị chặn cho database thật. Xem [`MIMIC_SQL_EXECUTION_GATE_REPORT.md`](MIMIC_SQL_EXECUTION_GATE_REPORT.md). Bốn SQL MIMIC vẫn chưa thực thi.

## Controlled constant smoke — 13/11/2026

- **IAM: `READ_ONLY_LIKELY`, chưa phải `VERIFIED_READ_ONLY`.** Theo kiểm tra của tài khoản Owner do người dùng cung cấp: service account chỉ có direct project role `roles/bigquery.jobUser`, HOSP/ICU cấp Data Viewer, 31/31 bảng không phát hiện `update/updateData/delete`. Policy Troubleshooter trả `Unknown` do thiếu quyền xem mọi Organization/Folder policy. Không thay đổi IAM. Bốn SQL đọc MIMIC tiếp tục **BLOCKED**.
- **Ngoại lệ được phê duyệt:** chỉ đúng `SELECT 1 AS smoke_constant`, dưới ADC impersonation target `kltn-sql-reader@kltn-text-to-sql.iam.gserviceaccount.com`. Method `execute_constant_smoke()` kiểm tra target ADC, không chấp nhận SQL đầu vào, dry run yêu cầu 0 bytes và dùng cap 10 MiB/timeout 15 giây. `BigQueryClient.execute()` và `BigQueryAdapter` vẫn tắt patient-data execution mặc định.
- **Constant SQL Execution: PASS.** Job `4b64ef9e-0d0e-494f-b902-72a56f1f2e70` hoàn thành không lỗi; đọc lại **chính job đã tạo** cho `smoke_constant=1`, đúng một hàng/một cột. Bytes processed **0**, bytes billed **0**, server execution latency **0.159 giây** (`ended-started`). Không tạo query job thứ hai để xác minh. SDK trả `job.schema=None` trên object ban đầu; đã sửa method dùng `iterator.schema` và kiểm tra bằng mock test, không chạy lại SELECT thật.
- **Metadata Access: PASS; Dry Run: PASS 5/5.** Không thực thi bốn SQL MIMIC, không gọi OpenAI/judge/benchmark. [Kết quả dry run và các SQL chờ phê duyệt](#dry-run-của-năm-sql-smoke) ở dưới.

## Lịch sử trước ngoại lệ constant

### ADC impersonation recheck — 12/11/2026

- **ADC Principal: PASS.** Trong `.venv_papers/clinsql`, `google.auth.default()` trả `google.auth.impersonated_credentials.Credentials`, target `kltn-sql-reader@kltn-text-to-sql.iam.gserviceaccount.com`. `GOOGLE_APPLICATION_CREDENTIALS` không được đặt, nên không ghi đè ADC. Không in token/credential contents.
- **Read-only IAM: BLOCKED để chứng nhận đầy đủ.** Hai dataset có direct access entry `READER` cho service account. `tables.testIamPermissions` trên **31/31 bảng** trả quyền `get/getData`, không trả `update/updateData/delete`; 0 HTTP errors. Khác với user ADC trước đó, principal này không có quyền ghi được phát hiện ở cấp bảng. Tuy vậy project IAM policy trả **403**, còn dataset `get_iam_policy` không khả dụng (BadRequest), nên chưa kiểm tra được mọi project/folder/group inheritance bằng nguồn độc lập. Google cảnh báo `testIamPermissions` có thể fail open; không dùng riêng kết quả âm tính này để chứng nhận read-only. Cần admin chạy IAM Policy Troubleshooter hoặc cung cấp effective IAM bindings cho service account đối với `bigquery.tables.update`, `updateData`, `delete` trên hai datasets; không gửi credentials. [BigQuery testIamPermissions](https://docs.cloud.google.com/bigquery/docs/reference/rest/v2/tables/testIamPermissions), [IAM Policy Troubleshooter](https://docs.cloud.google.com/iam/docs/troubleshooting-access).
- **Metadata Access: PASS.** Preflight mới dưới ADC impersonation đọc đủ 31 bảng tại `US`, critical columns/SQLGlot PASS, 4 INFORMATION_SCHEMA jobs + 31 table metadata reads, 0 patient-data SQL. Việc tạo 4 query jobs thành công xác minh `bigquery.jobs.create` bằng hành vi thực tế. Manifest cũ vẫn authoritative; preflight mới không ghi file. Hash preflight mới khác vì manifest bao gồm timestamp UTC.
- **Dry Run: PASS 5/5.** Các estimate giữ nguyên: constant 0; HOSP COUNT 0; ICU COUNT 0; JOIN 5,123,888; validation gold 043 20,032,585 bytes. Không thực thi bốn SQL MIMIC.
- **Constant SQL Execution lúc 12/11: BLOCKED.** Trạng thái này đã được thay bằng ngoại lệ được phê duyệt và kết quả PASS ngày 13/11 ở đầu báo cáo.
- **Sẵn sàng thực thi bốn SQL MIMIC: CHƯA.** Cần xác minh IAM ancestor hoặc quyết định rủi ro riêng và phê duyệt từng SQL/cap. ACL Windows hiện PASS nhưng retention MIMIC chưa được chốt. Offline tests hiện tại: **43 PASS**.

Tại thời điểm 12/11, execution bị chặn hoàn toàn. Ngày 13/11 người dùng đã phê duyệt ngoại lệ SELECT hằng duy nhất; bốn SQL MIMIC vẫn bị chặn do IAM chưa `VERIFIED_READ_ONLY`.

## IAM và principal — lịch sử trước ADC impersonation

- Trước khi impersonation, ADC loại user credential có quyền `update/updateData/delete` trên bảng đại diện của cả hai datasets; do đó execution đã bị chặn. Bằng chứng lịch sử này **không áp dụng** cho target service account mới.
- Application: `BigQueryClient` và `BigQueryAdapter` mặc định tắt data execution, chỉ cho một SELECT/CTE BigQuery, allowlist hai datasets và 31 bảng từ manifest, chặn DDL/DML, script nhiều statement và external access. Test offline PASS. Điều kiện IAM cần đạt **trước** khi bật execution flag.

## Dry-run của năm SQL smoke

Nguồn schema: `data/schema/manifests/mimiciv_3_1_20261112T143303Z.json`, SHA-256 `46a816c289178f5b69470fef4cf335f1ff556ad1f4d40b83d600517d76a0ab5d`. Tất cả dry run dùng BigQuery location `US`; chỉ kiểm tra kế hoạch/estimate, không trả dữ liệu. Chi phí USD bên dưới là ước tính upper approximation theo on-demand $6.25/TiB và mức tối thiểu 10 MiB mỗi bảng khi bytes > 0; thực tế phụ thuộc free tier/billing. [BigQuery pricing](https://cloud.google.com/bigquery/pricing).

1. **constant — DRY RUN PASS, EXECUTION PASS ngày 13/11:** 0 bytes; billed 0; cap 10 MiB. Không truy cập bảng. Kết quả đã quan sát `smoke_constant=1`, đúng một hàng/một cột, job không lỗi. Chi tiết job ID và latency ở đầu báo cáo.

   ```sql
   SELECT 1 AS smoke_constant
   ```

2. **hosp_patients_count — DRY RUN PASS:** 0 bytes; cost estimate $0; cap 10 MiB. Bảng `kltn-text-to-sql.mimiciv_3_1_hosp.patients`. Metadata `num_rows=364627` là tham chiếu gần nhất, có thể khác COUNT tại thời điểm chạy. PASS khi một giá trị COUNT không âm, tương thích metadata snapshot nếu dữ liệu không đổi. **Chỉ thực thi sau phê duyệt.**

   ```sql
   SELECT COUNT(*) AS n FROM `kltn-text-to-sql.mimiciv_3_1_hosp.patients`
   ```

3. **icu_icustays_count — DRY RUN PASS:** 0 bytes; cost estimate $0; cap 10 MiB. Bảng `kltn-text-to-sql.mimiciv_3_1_icu.icustays`. Metadata `num_rows=94458`; cùng điều kiện PASS và giới hạn như test 2. **Chỉ thực thi sau phê duyệt.**

   ```sql
   SELECT COUNT(*) AS n FROM `kltn-text-to-sql.mimiciv_3_1_icu.icustays`
   ```

4. **icu_hosp_join — DRY RUN PASS:** 5,123,888 bytes processed; cost estimate khoảng $0.00011921; cap đề xuất 20 MiB. Bảng `icu.icustays` và `hosp.admissions`. Chưa có reference result được xác minh. PASS khi query hoàn thành, trả một COUNT không âm, không vượt bytes cap/timeout; kiểm tra cardinality sau khi có phê duyệt. **Chỉ thực thi sau phê duyệt.**

   ```sql
   SELECT COUNT(*) AS n FROM `kltn-text-to-sql.mimiciv_3_1_icu.icustays` i
   JOIN `kltn-text-to-sql.mimiciv_3_1_hosp.admissions` a ON i.hadm_id = a.hadm_id
   ```

5. **clinsql_validation_043 — DRY RUN PASS:** 20,032,585 bytes processed; cost estimate khoảng $0.00011921; cap đề xuất 23 MiB (24,117,248 bytes). Bảng `hosp.patients`, `hosp.admissions`. Source gold validation `Patient_Demographics_and_Admissions/easy_level_queries/043/sql_043.sql` không sửa; chỉ thay project prefix trong SQL smoke ở bộ nhớ để dùng hai dataset được phép. Reference CSV chính thức ghi `iqr_in_hospital_mortality=0`; PASS khi query hoàn thành, trả đúng cột và so với reference theo chính sách diagnostic, không thay official scorer. **Chỉ thực thi sau phê duyệt.**

   ```sql
   SELECT
       APPROX_QUANTILES(a.hospital_expire_flag, 4)[OFFSET(3)] - APPROX_QUANTILES(a.hospital_expire_flag, 4)[OFFSET(1)] AS iqr_in_hospital_mortality
   FROM
       `kltn-text-to-sql.mimiciv_3_1_hosp.patients` AS p
   JOIN
       `kltn-text-to-sql.mimiciv_3_1_hosp.admissions` AS a
       ON p.subject_id = a.subject_id
   WHERE
       p.gender = 'F'
       AND p.anchor_age BETWEEN 51 AND 61
       AND a.dischtime IS NOT NULL;
   ```

## Executor, result handling và tests

- `BigQueryClient.execute` có dry run, bytes cap, timeout, result row cap và cancel job khi `result()` lỗi. Adapter giữ column names, BigQuery field types, job ID, bytes processed/billed và latency qua `Execution`; proposed runner giữ column types. Timeout, permission denied, bytes-cap exceeded và rejected SQL được test bằng fake SDK.
- `MeteredDatabase` mặc định chỉ log SQL, columns/types, row count, job ID, bytes, latency và status; `rows=null`. `capture_rows=True` nay chỉ chấp nhận synthetic mock. `ResultArtifactStore` tách rows khỏi logs, dùng file tạo độc quyền và SHA-256 để chấm lại prediction mà không gọi LLM. ACL thư mục `results/restricted` đã PASS; **chưa dùng cho MIMIC thật** cho đến khi chốt quyền lưu trữ/retention.
- Offline: **42 PASS** ở tests CLINSQL/BigQuery/security/schema/RAG/logging/baseline mock và result serialization; transport tests trước đó **2 PASS** riêng ngoài sandbox Windows. Legacy PostgreSQL/Mini tests vẫn lỗi collection do schema Mini đã xóa; không sửa/xóa trong giai đoạn này.
- Gold SQL/reference results/scorer và source ba paper không sửa. Hard/020 `NTILE(5)` vẫn là rủi ro diagnostic đã ghi trước đó. MAC-SQL/SDE-SQL không chạy trên BigQuery thật.

## Điều kiện để mở thực thi

1. ADC đã target đúng `kltn-sql-reader`; cần xác minh độc lập quyền kế thừa từ project/folder/group trên **cả hai datasets**. Chỉ chuyển Read-only IAM sang PASS khi admin/Policy Troubleshooter xác nhận service account không có quyền ghi.
2. Xác nhận cap/timeout cho từng SQL ở trên và phê duyệt **riêng** các test 2–5. Chỉ sau đó mới bật data execution có kiểm soát. SELECT constant có thể chạy trước nhưng vẫn cần tài khoản read-only theo protocol.
3. ACL result artifact store đã kiểm chứng; cần chốt quyền lưu trữ/retention trước khi lưu kết quả MIMIC. Logs không chứa raw rows và không truyền kết quả cho OpenAI.

**Danh sách chờ phê duyệt execution:** `hosp_patients_count`, `icu_icustays_count`, `icu_hosp_join`, `clinsql_validation_043`. `constant` đã PASS theo ngoại lệ riêng; bốn SQL MIMIC tiếp tục BLOCKED. Dừng tại báo cáo này.
