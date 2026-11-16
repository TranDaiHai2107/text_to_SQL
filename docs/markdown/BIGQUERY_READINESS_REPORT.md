# BigQuery readiness audit — 12/11/2026

**Kết luận:** Sẵn sàng cho bước **metadata-only integration có kiểm soát**, chưa sẵn sàng cho pilot GPT-5-mini, query MIMIC tốn phí, MAC-SQL/SDE-SQL thật hoặc benchmark test. Toàn bộ bằng chứng BigQuery hiện là thông tin người dùng cung cấp; audit này **không kết nối Google Cloud**, không gọi OpenAI/judge và không chạy patient SQL.

## PASS / FAIL / PENDING

- **PASS — Ranh giới CLINSQL:** `clinsql.runner` vẫn chỉ nhận `MockLLM`/`MockBigQuery`, validation-only. Source gốc ba paper và gold SQL/reference results/rubric chính thức không sửa. Dataset loader chỉ đọc `query_*.txt`; evaluator staging riêng mới dùng rubric sau khi prediction lưu.
- **PASS — Schema preparation:** inventory tên 22 HOSP/9 ICU không lấy từ Mini. Client đã chuẩn bị bốn truy vấn dataset `INFORMATION_SCHEMA.TABLES/COLUMNS`, kiểm tra đúng 31 bảng, vị trí cột, type, nullability; manifest version 1 và SHA-256; `schema_records_from_manifest` tạo lại input Schema RAG. Chưa tạo vector index vì chưa lấy metadata thật.
- **PASS — Application security offline:** BigQuery adapter và client kiểm tra SELECT/CTE, allowlist dataset (adapter còn giới hạn bảng theo manifest nếu có), chặn DDL/DML/external access; data execution tắt ở cả hai lớp mặc định. Khi bật có dry run, bytes billed cap, timeout, row limit và cancel khi `job.result` lỗi. Lỗi SQL ở adapter được redacted. Preflight chỉ đọc metadata khi có `--execute-metadata`; không còn CLI build Mini/app cũ. `FullAgentic.answer` bị chặn trong profile CLINSQL nên không tự gửi aggregate hoặc raw query results sang LLM. Mock runner chỉ lưu raw rows tổng hợp; production logging phải giữ `capture_rows=False`.
- **PENDING — IAM và Google Cloud:** chưa có credentials/location/billing project ở audit; không thể xác minh service account thực tế chỉ có `bigquery.jobs.create` ở billing project và quyền đọc metadata/table data ở hai datasets, hay không có quyền ghi. Người dùng báo đã import 31 bảng, counts/types và 6/6 JOIN; chưa xác nhận độc lập.
- **PASS — Evaluation boundary:** gold SQL/reference CSV và scorer gốc được giữ nguyên. Chính sách diagnostic cho FLOAT, duplicate, NULL, unordered/incomplete results tại `CLINSQL_RESULT_COMPARISON_POLICY.md`; không thay metric chính thức. Validation `Disease_Diagnosis_and_Outcomes/hard_level_queries/020` có `NTILE(5)` chỉ `ORDER BY composite_risk_score`, có thể đổi bucket khi tie; cần kiểm tra bằng query được duyệt. Test gold/rubric không đi vào inference/retrieval.
- **PASS — Offline CLINSQL-related tests:** 35 tests của CLINSQL adapter, BigQuery adapter/client/preflight, schema/SQL guard, RAG, logging, evaluator mock và baseline workflows qua (`test_agentic_evidence`, `test_agentic_selection`, `test_clinsql_foundation`, `test_clinsql_offline_workflows`). Hai transport tests riêng qua khi chạy ngoài sandbox Windows; dùng `httpx.MockTransport`, không gọi mạng.
- **FAIL — Full repository suite:** dừng ở collection với bốn module legacy (`test_agentic_ui`, `test_dataset_integrity`, `test_evaluation`, `test_sql_validator`) còn import `mimic_schema.json` đã xóa. Đây là đường PostgreSQL/Mini bị retire, chưa cập nhật/loại bỏ các legacy tests. Không ghi toàn suite PASS.
- **PENDING — Fidelity/cost:** MAC-SQL và SDE-SQL vẫn là port mock chưa đủ fidelity theo `BASELINE_ADAPTATION.md`; scorer/judge chính thức, GPT-5-mini snapshot, giá/cost và truyền probe evidence chưa xác minh.
- **PENDING — Result persistence:** evaluator thật cần result artifact cho chấm lại; production path hiện chưa có kho lưu kết quả hạn chế truy cập tách khỏi logs. Phải thiết kế quyền đọc/lưu/retention trước khi thực thi patient SELECT, không bật `capture_rows` trong trace/log để thay thế.

## Pre-integration audit và file sửa

Client thật đã có interface `dry_run`, `execute` và `load_schema_manifest`; adapter giữ dry run/cap/allowlist; `Schema.from_records` và Schema RAG nhận records từ manifest; offline workflows và evaluator không cần làm lại. Để chuyển mock sang thật còn cần wiring provider có ghi usage/resume, kết nối BigQuery có kiểm soát, schema thật, IAM/policy và pilot validation. Không dùng `mock_schema_records` cho real run.

File sửa hoặc tạo trong audit hiện được tập trung tại `docs/markdown/`, gồm `PROJECT_README.md`, `EXPERIMENT_PROTOCOL.md`, `IMPLEMENTATION_STATUS.md`, `BASELINE_ADAPTATION.md`, `LEGACY_DEPENDENCY_AUDIT.md`, `CLINSQL_RESULT_COMPARISON_POLICY.md` và báo cáo này; code liên quan gồm `.env.example`, `run.py`, `src/ehrqa/clinsql/metadata.py`, `bigquery_client.py`, `bigquery_adapter.py`, `src/ehrqa/cli/bigquery_preflight.py`, `src/ehrqa/agentic/schema.py`, `pipeline.py`, `tests/test_clinsql_offline_workflows.py`. Đã xóa `data/schema/mimic_schema.json` và `src/ehrqa/cli/build_mimic_mini.py`; các entrypoint PostgreSQL/Mini rời khỏi `run.py`. Code ứng dụng tiếng Việt/legacy khác vẫn ở repo để tham khảo nhưng không chạy được nguyên trạng; không dùng cho CLINSQL.

Transport test treo trong sandbox tại `asyncio.run` → Windows `ProactorEventLoop` → `socket.socketpair()` trước khi HTTP mock được gọi. Dừng lượt đó; chạy cùng hai test ngoài sandbox cho kết quả **2 passed in 0.28s**. Full suite ngoài sandbox dừng sau **4 collection errors** nói trên, không chạy hết suite.

## Cần BigQuery thật để xác minh

1. Xác nhận `BQ_LOCATION`, `BQ_BILLING_PROJECT`, principal/credentials và quyền MIMIC hợp lệ. IAM cần tối thiểu job creation tại billing project và data viewer trên **đúng hai datasets**, không cấp quyền update/create/delete table. Kiểm tra quyền ở IAM và thử metadata-only với principal dùng pilot.
2. Chạy preflight metadata được phê duyệt: bốn dataset INFORMATION_SCHEMA reads và 31 `get_table` metadata calls; đối chiếu 22/9 bảng, columns/types/nullability, row-count metadata và lưu manifest bất biến kèm SHA-256. Chưa chạy lệnh này trong audit.
3. Từ manifest thật dựng lại Schema RAG; kiểm tra parser với type thực tế, JOIN metadata và table alias `datetimeevents` (source CLINSQL text từng ghi `datetimesevents`). Khóa schema hash.
4. Thử dry run của một số SELECT/JOIN smoke được duyệt và xác nhận estimate, `maximum_bytes_billed`, timeout, location và lỗi permission/quota thực tế. Không thực thi SQL patient-data trước khi được duyệt trần chi phí.
5. Với bất kỳ probe nào, chốt chính sách value evidence/rows/errors được phép gửi tới LLM. Mặc định không log raw patient rows và không gửi query results lên API.

## Điều kiện trước pilot GPT-5-mini

- Metadata/IAM checks trên principal thật PASS; schema manifest và source benchmark được khóa hash; dry-run và SQL guard được xác nhận trên BigQuery thật.
- Quyền lưu trữ/truyền dữ liệu MIMIC, logging/redaction, phạm vi probe và bytes cap/timeout/row cap được chốt. Nếu SDE-SQL không thể nhận probe evidence đúng thuật toán, báo adapted/restricted hoặc blocker, không báo reproduction.
- Xác minh model ID/snapshot, inference transport/usage/cost, resume không gọi API lặp, ngân sách trần và tách inference cost khỏi judge cost; được người dùng phê duyệt trước khi gọi trả phí.
- Có nơi lưu result artifact theo quyền MIMIC và khả năng re-score predictions đã lưu; logs chỉ giữ metadata, SQL, counts và error đã redacted.
- Xác minh official scorer/judge trên validation, comparison diagnostics và rủi ro Hard/020; khóa evaluator/judge config. Không dùng test gold để chỉnh hệ thống.
- MAC/SDE cần hoàn tất fidelity so với source gốc theo adaptation log trước khi đưa vào pilot so sánh; không tự giảm số agent/probe/correction.

## Bước kết nối tối thiểu đề xuất

Điền `BQ_LOCATION` và `BQ_BILLING_PROJECT` vào môi trường riêng, dùng principal read-only đã kiểm tra IAM. Sau đó chạy `python run.py bigquery-preflight` để xem offline plan, rồi **sau khi duyệt metadata access** chạy `python run.py bigquery-preflight --execute-metadata --manifest-path <đường dẫn versioned>`; lệnh thứ hai chỉ dùng metadata và không chạy COUNT/JOIN patient tables. Đọc report và manifest, kiểm tra hash/tên bảng/type. Bước dry-run smoke và mọi query có bytes billed là một phê duyệt riêng. Không tự động chuyển sang pilot API.
