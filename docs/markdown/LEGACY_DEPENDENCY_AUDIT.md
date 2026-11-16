# Audit ranh giới EHRSQL/PostgreSQL/MIMIC Mini

Kiểm tra offline ngày 12/11/2026 trên `src/ehrqa/` và `run.py`. Đường benchmark chính đi qua `ehrqa.clinsql` và phần dùng chung trong `ehrqa.text2sql`/`ehrqa.agentic`. CLI PostgreSQL/Mini đã tắt; schema Mini và script build Mini đã xóa. Các source legacy khác chỉ còn để tham khảo, không chạy được nguyên trạng.

## Các phụ thuộc legacy đã khoanh vùng

- `src/ehrqa/app.py` và `src/ehrqa/rag_engine.py`: giao diện tiếng Việt, kết nối PostgreSQL, prompt SQL PostgreSQL, chạy và diễn giải kết quả. **Không được import bởi** `ehrqa.clinsql.runner`.
- `src/ehrqa/config.py`: DSN PostgreSQL, đường schema/examples/test cũ. Nhánh mới dùng `ehrqa.clinsql.config.BigQueryConfig` và `ExperimentConfig`.
- `src/ehrqa/agentic/adapters.py`: `PostgresDatabase`, catalog lookup bằng SQL/PostgreSQL và `application_pipeline`. Nhánh mới dùng `ehrqa.clinsql.proposed.PipelineDatabase` cùng BigQuery adapter hoặc mock.
- `src/ehrqa/agentic/prompts.py`: chứa cả profile PostgreSQL/Mini và profile CLINSQL/English. Pipeline chung chọn profile `clinsql`; benchmark không gọi bước answer tiếng Việt.
- `src/ehrqa/agentic/retrieval.py`: `SequentialRAG` và schema lexical là core dùng chung; hàm `catalog_search` dùng placeholder/SQL kiểu legacy, chỉ được gọi từ Postgres adapter cũ. Nhánh CLINSQL dùng callback catalog ICD được phép và không dùng hàm này.
- `src/ehrqa/agentic/schema.py`, `contracts.py`, `evidence.py`, `pipeline.py`: parser/validation, kiểm tra evidence và self-correction dùng chung theo `schema.dialect`. `schema.py` đã ngừng import validator PostgreSQL để lấy danh sách hàm cấm; danh sách trung lập ở `ehrqa.text2sql.security`. Những mặc định `sqlite` trong utility chỉ dùng khi caller không truyền dialect; nhánh CLINSQL truyền `bigquery` từ Schema.
- `src/ehrqa/sql_validator.py`: validator PostgreSQL của ứng dụng cũ. Benchmark dùng `agentic.schema.Schema.inspect` và `clinsql.bigquery_adapter.BigQueryAdapter`.
- `build_mimic_mini.py` đã xóa. `build_vector_db.py`, `evaluate.py`, `expand_test_dataset.py` là source legacy không còn entrypoint trong `run.py`; không dùng vector index cũ hoặc dữ liệu test cũ để chọn few-shot.
- `src/ehrqa/agentic/budget.py`: SQLite chỉ là storage cho budget cục bộ, không phải MIMIC database; không dùng trong runner CLINSQL hiện tại.
- `data/schema/mimic_schema.json` đã xóa. `clinsql.metadata` chỉ giữ inventory tên 22 HOSP/9 ICU để kiểm tra đầy đủ; cột/type thật phải đến từ `INFORMATION_SCHEMA` và manifest có hash. Mock dùng schema tổng hợp, không là authoritative.

## Đường CLINSQL hiện tại

`clinsql.dataset` chỉ trả question metadata; `clinsql.runner` chỉ nhận `MockLLM` và `MockBigQuery`, validation only. `clinsql.proposed` tái sử dụng pipeline agentic với `BigQuery` schema, callbacks ICD/few-shot được kiểm soát. `clinsql.baselines` dùng dependency injection; evaluator staging chỉ đọc rubric sau khi prediction đã lưu. `clinsql.bigquery_client` chưa được khởi tạo trong bất kỳ test/runner nào; preflight mặc định chỉ in plan.

## Ranh giới còn phải kiểm tra khi chuyển sang môi trường thật

1. So sánh đủ 31 bảng, tên cột, type, mode và vị trí dataset từ BigQuery thật; đặc biệt source CLINSQL text ghi `datetimesevents`, inventory nội bộ ghi `datetimeevents`. Không tự đổi tên bảng theo một tài liệu chưa xác minh.
2. Xác nhận output của các stage chỉ chứa schema/catalog được phép, không chứa raw rows hoặc thống kê bệnh nhân gửi tới LLM. Mọi probe policy cho MAC/SDE cần duyệt riêng.
3. Thay schema provisional bằng metadata BigQuery được xác minh và khóa hash trước pilot; không đưa gold/rubric test vào inference.
4. Benchmark runner thực tế cần model transport, limit/billing guard, persist/resume, evaluator/judge config và artifact mapping được kiểm chứng end-to-end. Mock offline hiện không chứng minh các mục này.
