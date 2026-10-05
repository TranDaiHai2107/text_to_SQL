# Hướng dẫn cài đặt và vận hành

Tài liệu này dùng cho Windows PowerShell. Quy trình đầy đủ và mô tả kiến trúc nằm trong [README.md](README.md).

## 1. Chuẩn bị

- Python 3.12.
- Docker Desktop.
- Quyền truy cập hợp lệ vào MIMIC-IV 3.1.
- Groq API key.

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
Copy-Item .env.example .env
```

Điền `GROQ_API_KEY`, `DB_PASS`, `DB_LOADER_PASS` và `MIMIC_DATA_DIR` trong `.env`. Ứng dụng dùng role `mimic_reader`; loader dùng role quản trị riêng.

## 2. PostgreSQL

```powershell
docker compose up -d postgres
docker compose ps
```

Init script chỉ chạy khi volume được tạo lần đầu. Nó tạo `mimic_reader`, cấp quyền đọc và bật `default_transaction_read_only` cho role này.

## 3. Nạp dữ liệu

```powershell
python build_mimic_mini.py
```

Script nạp 31 bảng qua staging table, giữ kiểu DATE/TIMESTAMP, tạo index và làm mới quyền SELECT của runtime role. Subset mặc định gồm 500 bệnh nhân, được lấy mẫu có bao phủ mã ICD trong benchmark và cohort ICU.

## 4. Dựng ChromaDB

```powershell
python build_vector_db.py
```

Kết quả kỳ vọng:

- `icd_dictionary`: tối đa 10.000 mã ICD phổ biến theo tần suất sử dụng.
- `schema_dictionary`: 31 bảng.
- `sql_examples`: 101 ví dụ production.
- `sql_examples_eval`: 73 ví dụ sau khi loại 28 SQL trùng gold test.

Nếu PostgreSQL chưa chạy, ICD có thể được dựng từ CSV gốc:

```powershell
python build_vector_db.py --collections icd_dictionary --icd-source csv
```

## 5. Kiểm thử và chạy ứng dụng

```powershell
python -m unittest discover -s tests -v
python -m streamlit run app.py
```

Ứng dụng mặc định không gửi các dòng kết quả MIMIC trở lại LLM. Đặt `SEND_RESULTS_TO_LLM=true` chỉ khi việc này phù hợp với điều khoản sử dụng dữ liệu và chính sách lưu giữ của nhà cung cấp.

## 6. Đánh giá

```powershell
python evaluate.py --quick --modes base full full_agentic
python evaluate.py --modes full full_agentic
```

Trước khi gọi LLM, script thực thi preflight toàn bộ gold SQL. Nếu một gold query lỗi, evaluation dừng và in rõ ID cần sửa. `full` và `full_agentic` dùng `sql_examples_eval`, nên không lấy các few-shot trùng đáp án test.

## 7. Lỗi thường gặp

- `connection refused`: mở Docker Desktop và chạy `docker compose up -d postgres`.
- Collection thiếu hoặc sai số lượng: chạy lại `python build_vector_db.py`.
- Sai embedding model: giữ cùng giá trị `EMBEDDING_MODEL` khi build và khi chạy app.
- `mimic_reader` chưa tồn tại trên volume cũ: tạo role read-only thủ công hoặc khởi tạo một volume PostgreSQL mới.
- Rate limit Groq: giảm số mode/câu đánh giá; retry ngắn trong code chỉ xử lý lỗi tạm thời, không thay đổi quota tài khoản.
