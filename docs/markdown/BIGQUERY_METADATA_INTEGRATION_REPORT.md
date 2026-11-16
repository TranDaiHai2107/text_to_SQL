# BigQuery Metadata Integration — 12/11/2026

## Kết quả

**PASS cho metadata integration.** ADC trên Windows hoạt động. Hai dataset `kltn-text-to-sql.mimiciv_3_1_hosp` và `kltn-text-to-sql.mimiciv_3_1_icu` cùng ở location `US`. Preflight chạy đúng 4 truy vấn dataset `INFORMATION_SCHEMA.TABLES/COLUMNS` và 31 lệnh đọc table metadata; **0 truy vấn trên hàng dữ liệu bệnh nhân**, 0 COUNT/JOIN, 0 OpenAI/judge/benchmark test.

- Bảng phát hiện: **22 HOSP + 9 ICU = 31**, khớp inventory MIMIC-IV v3.1 đã chuẩn bị.
- Columns, data types, ordinal positions và nullability được lưu trong manifest từ BigQuery thật. Kiểm tra các cột khóa quan trọng: **PASS**; `datetimeevents`: **có**.
- SQLGlot: lần preflight ban đầu báo thiếu package trong venv CLINSQL. Đã cài `sqlglot 30.21.0`; kiểm tra lại manifest đã lưu **offline PASS**, không phát sinh thêm query job.
- Schema validation cuối: `pass=true`, `missing_critical_columns={}`, `sqlglot_error=null`.
- Manifest authoritative: [`data/schema/manifests/mimiciv_3_1_20261112T143303Z.json`](data/schema/manifests/mimiciv_3_1_20261112T143303Z.json). `manifest_version=1`, có timestamp UTC, project/dataset IDs, location và 31 schema entries.
- SHA-256: `46a816c289178f5b69470fef4cf335f1ff556ad1f4d40b83d600517d76a0ab5d` (hash được kiểm lại offline).

## Credentials và IAM

ADC file đã được nhận diện và BigQuery SDK dùng được; không đọc hoặc hiển thị token. Hai lệnh `get_dataset`, bốn INFORMATION_SCHEMA jobs và 31 `get_table` calls thành công, chứng minh principal hiện tại có quyền đọc metadata và tạo query jobs cần cho preflight. **Chưa xác minh danh tính principal hay toàn bộ effective IAM bindings**, nên chưa thể kết luận principal không có quyền ghi. Application vẫn tắt patient-data execution mặc định và chặn DDL/DML. `gcloud` không có trong PATH của phiên Codex dù ADC hoạt động.

## Chi phí và giới hạn

Bốn INFORMATION_SCHEMA queries có `maximum_bytes_billed=10,485,760` bytes/query và timeout 30 giây; Google Cloud có mức tính phí on-demand tối thiểu 10 MiB cho mỗi query INFORMATION_SCHEMA và không cache loại query này. [Tài liệu BigQuery INFORMATION_SCHEMA](https://docs.cloud.google.com/bigquery/docs/information-schema-intro). Lần kiểm tra SQLGlot sau khi cài package chỉ đọc manifest trên đĩa.

## Readiness bước kế tiếp

**Chưa mở SQL Execution Smoke Test.** Trước bước đó cần kiểm tra effective IAM/read-only của principal, chốt SQL smoke và bytes cap, chính sách lưu result artifacts, và phê duyệt riêng việc thực thi query có thể đọc dữ liệu MIMIC. Schema RAG có thể dựng lại từ manifest này qua `schema_records_from_manifest`; chưa tạo vector index hoặc gọi LLM. Gold SQL/reference results/scorer CLINSQL giữ nguyên; Hard/020 `NTILE(5)` vẫn được theo dõi theo comparison policy.

Offline tests gần nhất: **36 PASS** cho CLINSQL/BigQuery/RAG/logging/baseline mock; **2 transport PASS** riêng ngoài sandbox Windows. Full suite còn **4 collection errors** ở tests legacy PostgreSQL/Mini do `mimic_schema.json` đã xóa. Không sửa/xóa tests đó trong giai đoạn hiện tại; khi migration tiếng Việt về sau, chuyển chúng sang fixture manifest BigQuery và mock executor, đồng thời giữ kiểm thử RAG, conversation, correction và interpretation.

Theo quyết định làm rõ của người dùng, **không tạo** `VIETNAMESE_SYSTEM_BIGQUERY_MIGRATION_PLAN.md` và không sửa hệ thống tiếng Việt ở giai đoạn này.
