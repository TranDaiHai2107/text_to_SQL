# Dữ liệu hiện có và dữ liệu mục tiêu

Code ứng dụng cũ PostgreSQL/tiếng Việt dùng `queries/mimic_examples.json` (101 cặp hỏi–SQL), `queries/test_dataset.json` (180 câu nội bộ), `queries/test_multiturn.json` và `schema/mimic_schema.json` (31 bảng). `raw/mimic-iv-3.1/`, vector index và backups là dữ liệu cục bộ ngoài Git.

Đích triển khai chung là MIMIC-IV v3.1 BigQuery; benchmark chính dùng câu hỏi tiếng Anh, split và ground truth CLINSQL 2026 chính thức. Chưa nhập dataset hoặc kết nối DB vào repo. Loader `src/ehrqa/clinsql/dataset.py` chỉ xuất trường câu hỏi cho inference và khóa test mặc định. Không dùng bộ 180 câu hoặc MIMIC Mini để báo điểm CLINSQL.
