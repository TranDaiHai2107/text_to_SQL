# Phase A — MIMIC-IV SQL Smoke Test: checklist phê duyệt

Ngày chuẩn bị: 13/11/2026. **Tài liệu này là checklist trước khi chạy, đã được thay thế bởi [kết quả Phase A](PHASE_A_EXECUTION_RESULTS.md).** Người dùng đã đưa quyết định risk acceptance cấp project và bốn SQL đã PASS 4/4. Nội dung thiếu phê duyệt bên dưới ghi lại trạng thái lịch sử trước quyết định đó; không dùng để mô tả trạng thái hiện tại. Hồ sơ mẫu vẫn là [`docs/PHASE_A_APPROVAL_DRAFT.json`](docs/PHASE_A_APPROVAL_DRAFT.json).

## 1. Điều kiện đã PASS

- ADC trong Python environment `.venv_papers/clinsql` là `google.auth.impersonated_credentials.Credentials`, target `kltn-sql-reader@kltn-text-to-sql.iam.gserviceaccount.com`; `GOOGLE_APPLICATION_CREDENTIALS` không ghi đè. Runner còn kiểm tra chính credential của BigQuery SDK client trước dry run/execution trong mode được phê duyệt. Không dùng Owner credential.
- Manifest authoritative `data/schema/manifests/mimiciv_3_1_20261112T143303Z.json`: 31 bảng, SHA-256 `46a816c289178f5b69470fef4cf335f1ff556ad1f4d40b83d600517d76a0ab5d`. Project `kltn-text-to-sql`, HOSP/ICU và location `US` khớp draft.
- Bốn SQL Phase A trong `bigquery_sql_smoke.py` khớp 4/4 SHA-256 đã khóa trong `execution_control.py` và draft. Caps tương ứng 10/10/20/23 MiB, timeout 30 giây. Dry run BigQuery của cả bốn đã PASS trong đợt trước; lượt chuẩn bị này kiểm lại hash/parser **offline**, không tạo BigQuery job mới.
- `results/restricted` hiện rỗng và bị loại khỏi Git. ACL Windows verifier trả `safe=true`, inheritance disabled, 0 unexpected rules. ACL cho phép tài khoản hiện hành, SYSTEM và nhóm Administrators; nhóm Administrators cục bộ hiện liệt kê `Administrator` và `ASUS`. Đây là kiểm tra kỹ thuật, chưa phải xác nhận tuân thủ chính sách truy cập dữ liệu.
- Runner mặc định `PLAN_ONLY`; kiểm tra lệnh này bằng đúng Python environment đã PASS, `patient_sql_executed=0`. `--execute-approved` cần hồ sơ hợp lệ đặt trong `results/restricted`. Marker `phase_a_<case_id>.started` được tạo độc quyền **trước** query job và giữ lại sau lỗi; approval ID mới không cho tự chạy lại cùng case. Result artifact chỉ nhận đúng một hàng/một cột, tách khỏi summary/log; SQL Guard, allowlist, dry run, `maximum_bytes_billed`, timeout và cancellation vẫn bật. Query cache reuse được tắt cho execution; BigQuery vẫn có thể lưu temporary result table.
- Offline tests liên quan Phase A, security, transport, logging và mock workflows: **50 PASS** sau sửa marker và scalar-result guard. Không gọi OpenAI/judge/benchmark.

## 2. Điều kiện còn thiếu — giữ gate đóng

1. **Thẩm quyền và Organization policy:** IAM chỉ `READ_ONLY_LIKELY`. Direct project role là BigQuery Job User, hai datasets là Data Viewer, 31/31 bảng không thấy quyền ghi qua `testIamPermissions`, nhưng project/Folder/Organization inheritance, group bindings và policy cấp trên chưa thể chứng nhận. Owner-run Policy Troubleshooter trước đó là `Unknown`. Cần người có thẩm quyền xác nhận có thể chấp nhận rủi ro này và không vi phạm Organization policy bắt buộc; nếu không có bằng chứng hợp lệ, **không điền** `organization_policy_clearance_reference` và không chạy.
2. **Chấp nhận rủi ro:** `risk_acknowledged` vẫn `false`. Người phê duyệt phải ghi rõ phần IAM chưa biết, bốn case duy nhất, caps/timeout/output, khoảng thời gian hiệu lực và việc dùng reader service account. Không biến trạng thái thành `VERIFIED_READ_ONLY` khi chưa có chứng cứ mới.
3. **Result storage và retention:** chưa có quyết định được cung cấp về thời hạn lưu artifact local, người được phép truy cập (gồm tài khoản hiện hành, SYSTEM, local Administrators), backup/sync/indexing, lịch xóa và nơi lưu bằng chứng audit. `result_storage_policy_reference` còn trống. [PhysioNet DUA 1.5.0](https://physionet.org/content/mimiciv/view-dua/3.1/) yêu cầu bảo vệ dữ liệu và không chia sẻ quyền truy cập; văn bản công khai này **không ấn định một số ngày retention cho artifact cục bộ**. Cần áp dụng chính sách tổ chức và điều kiện truy cập MIMIC của người dùng trước khi lưu kết quả thật.
4. **BigQuery temporary results:** BigQuery mặc định lưu output query trong bảng tạm; [Google nêu thời gian tồn tại tối đa khoảng 24 giờ và quyền truy cập hạn chế cho principal tạo job](https://docs.cloud.google.com/bigquery/docs/writing-results). Tắt `use_query_cache` chỉ ngăn tái sử dụng kết quả cache, không loại bỏ bảng kết quả tạm. Người phê duyệt cần xác nhận cơ chế này phù hợp chính sách lưu trữ hiện hành; không tạo permanent destination table.
5. **Hồ sơ cuối:** chưa có file approval hoàn tất trong `results/restricted`. `approval_id`, `approver`, `authority`, `organization_policy_clearance_reference`, `risk_acknowledged`, `valid_from_utc`, `valid_until_utc` và `result_storage_policy_reference` không được tự điền bằng giả định. Cần kiểm tra lại ADC, ACL, hash/manifest và hiệu lực ngay trước mỗi case.

## 3. Các trường anh cần xác nhận trong hồ sơ

Các trường đã cố định từ yêu cầu và code: `principal`, `project_id`, `datasets`, `location`, `manifest_sha256`, `phase=phase_a_smoke`, bốn `sql_sha256_by_case`, bốn `max_bytes_billed_by_case`, `timeout_seconds=30`. `iam_status` trong file là **execution mode** `READ_ONLY_LIKELY_WITH_APPROVED_RISK`; trạng thái bằng chứng IAM vẫn là **`READ_ONLY_LIKELY`**.

Cần xác nhận hoặc cung cấp bằng chứng hợp lệ cho:

- `approval_id`: mã quyết định duy nhất; không tái sử dụng cho quyết định khác.
- `approver`: tên/định danh người phê duyệt thực tế.
- `authority`: cơ sở thẩm quyền đối với project, MIMIC và chính sách tổ chức; không suy từ quyền Owner đơn thuần.
- `organization_policy_clearance_reference`: tài liệu/biên bản/quyết định cho phép thực hiện trong khi IAM inheritance còn chưa rõ, hoặc bằng chứng của administrator về policy bắt buộc. Không điền chỉ bằng lời khẳng định kỹ thuật từ ứng dụng.
- `risk_acknowledged=true`: chỉ khi người có thẩm quyền chấp nhận **rõ ràng** rủi ro IAM còn lại cho đúng phạm vi Phase A.
- `valid_from_utc` và `valid_until_utc`: cửa sổ thời gian có timezone UTC; gate từ chối ngoài cửa sổ.
- `result_storage_policy_reference`: quyết định ghi rõ `results/restricted`, mục đích giữ scalar artifacts cho audit/evaluation, thời hạn retention, cách xóa, quyền truy cập của current user/SYSTEM/Administrators, backup/sync, và việc BigQuery có temporary results. ACL kỹ thuật đã PASS nhưng nội dung chính sách chưa xác nhận.
- Output: xác nhận **một hàng/query**. Draft ghi `max_rows=2` vì SDK fetch thêm một hàng làm sentinel phát hiện truncation; adapter chỉ trả/lưu tối đa **một** hàng và runner từ chối kết quả không đúng một scalar. Đây không phải phê duyệt lưu hai hàng.

Chỉ sau khi các mục trên được xác nhận, tạo một file approval hoàn tất trong `results/restricted/phase_a_approval.json`; giữ bản nháp trong `docs/` ở trạng thái chưa được phê duyệt. Ứng dụng xác minh cấu trúc, scope, hash, giới hạn và thời hạn; **không thể tự chứng nhận thẩm quyền hoặc tính hợp lệ pháp lý của nội dung do người ký cung cấp**.

## 4. Phạm vi risk acceptance

Chỉ cho phép service account `kltn-sql-reader` thực hiện đúng bốn SELECT đã khóa hash trên hai datasets MIMIC-IV v3.1 tại US, một case mỗi lệnh. `hosp_patients_count` 10 MiB, `icu_icustays_count` 10 MiB, `icu_hosp_join` 20 MiB, `clinsql_validation_043` 23 MiB; timeout 30 giây/query, output một scalar. Không cho phép DDL/DML, script, external functions, project/dataset khác, tăng cap, bỏ SQL Guard, Owner credentials, chạy batch, LLM API hoặc judge. Quyết định Phase A không mở Phase B/C/D.

Tổng cap **63 MiB = 66,060,288 bytes**. Nếu toàn bộ bị tính phí theo on-demand **$6.25/TiB**, giới hạn giá trị quét theo cap xấp xỉ **$0.000376** trước free tier và thuế/quy đổi; thực tế có thể bằng 0 hoặc khác do billing plan, mức tối thiểu trên mỗi bảng và cache. Đây là phép tính theo cap, không phải hóa đơn. [Giá và quy tắc tính phí BigQuery](https://cloud.google.com/bigquery/pricing).

## 5. Lệnh chính xác sau khi hồ sơ hợp lệ

Chạy từ `D:\Github\text_to_SQL` bằng PowerShell. Các dòng dưới đây **chỉ để chuẩn bị và review; không chạy trong nhiệm vụ này**. File approval ở đường dẫn dưới đây hiện chưa tồn tại. Thiết lập environment một lần:

```powershell
$env:BQ_PROJECT_ID = 'kltn-text-to-sql'
$env:BQ_HOSP_DATASET = 'mimiciv_3_1_hosp'
$env:BQ_ICU_DATASET = 'mimiciv_3_1_icu'
$env:BQ_LOCATION = 'US'
$env:BQ_BILLING_PROJECT = 'kltn-text-to-sql'
```

Sau khi phê duyệt, chạy **từng lệnh riêng** và kiểm tra summary/job trước khi chuyển sang lệnh tiếp theo:

```powershell
.\.venv_papers\clinsql\Scripts\python.exe run.py bigquery-approved-smoke --case-id hosp_patients_count --manifest data/schema/manifests/mimiciv_3_1_20261112T143303Z.json --approval results/restricted/phase_a_approval.json --execute-approved
```

```powershell
.\.venv_papers\clinsql\Scripts\python.exe run.py bigquery-approved-smoke --case-id icu_icustays_count --manifest data/schema/manifests/mimiciv_3_1_20261112T143303Z.json --approval results/restricted/phase_a_approval.json --execute-approved
```

```powershell
.\.venv_papers\clinsql\Scripts\python.exe run.py bigquery-approved-smoke --case-id icu_hosp_join --manifest data/schema/manifests/mimiciv_3_1_20261112T143303Z.json --approval results/restricted/phase_a_approval.json --execute-approved
```

```powershell
.\.venv_papers\clinsql\Scripts\python.exe run.py bigquery-approved-smoke --case-id clinsql_validation_043 --manifest data/schema/manifests/mimiciv_3_1_20261112T143303Z.json --approval results/restricted/phase_a_approval.json --execute-approved
```

Lệnh `PLAN_ONLY` bỏ `--approval` và `--execute-approved`; nó không tạo BigQuery job. Không xóa marker để chạy lại một case nếu chưa điều tra job và có quyết định mới.

## 6. Điều kiện dừng

Dừng trước job nếu approval thiếu/không có thẩm quyền/hết hạn, Organization policy hoặc storage decision không rõ, ADC hay SDK client không phải reader, ACL không đạt, manifest/SQL hash lệch, marker đã tồn tại, SQL Guard từ chối, dry run lỗi hoặc vượt cap. Sau job, dừng nếu BigQuery trả `PERMISSION_DENIED`, bytes cap exceeded, timeout/cancel, result shape không đúng một scalar, artifact ghi lỗi hoặc job status không rõ. Giữ marker và job ID/bằng chứng hiện có để điều tra; **không tự tăng cap, đổi principal, bỏ guard, xóa marker hay tự chạy lại**. Nếu phát hiện reader có quyền ghi ngoài dự kiến, dừng toàn bộ Phase A và báo cáo.

Không truyền result hay clinical values lên OpenAI, không gọi GPT-5-mini hoặc CLINSQL judge, không chạy benchmark, không xử lý hệ thống tiếng Việt.
