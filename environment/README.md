# Môi trường riêng cho hai source paper (CLINSQL CoT, SDE-SQL)

Đã tạo trên Windows/Python 3.12.4 ngày 12/11/2026. Các venv ở `.venv_papers/` được Git ignore; lock package đã cài nằm trong `environment/locks/`. Source gốc vẫn nằm ở `external/` và không bị sửa.

| Môi trường | Dependency đã cài | Smoke check offline |
| --- | --- | --- |
| `.venv_papers/clinsql` | `requirements-clinsql-proprietary.txt`, subset của requirements gốc cho CoT proprietary + rubric scorer. Không cài vLLM/ray/torch/transformers của nhánh open-source. | Native CoT `--help`, scorer `--help`, `pip check` thành công |
| `.venv_papers/sde_sql` | Toàn bộ `external/sde_sql_official/requirements.txt`, gồm torch, transformers, `sqlglot==25.6.1`. | Native `gpt_request.py --help`, `pip check` thành công |

`--help` và import không chứng minh kết quả inference tương đương. Các lock là snapshot của Python 3.12 trên Windows, không phải dependency lock do tác giả phát hành. Vì `requirements.txt` gốc phần lớn không pin phiên bản, tái tạo môi trường nguyên thời điểm paper sẽ cần thêm metadata/tags từ tác giả.

Tạo lại venv trong PowerShell từ repo root:

```powershell
py -3.12 -m venv .venv_papers/clinsql
py -3.12 -m venv .venv_papers/sde_sql
.\.venv_papers\clinsql\Scripts\python.exe -m pip install -r environment/locks/clinsql-py312-win.txt
.\.venv_papers\sde_sql\Scripts\python.exe -m pip install -r environment/locks/sde_sql-py312-win.txt
```

Không dùng native script để chạy CLINSQL test hoặc BigQuery trước khi khóa cấu hình, quyền truy cập và ngân sách. Native SDE còn phụ thuộc file BIRD/Spider ngoài checkout. Thí nghiệm chính chạy pipeline từ `.venv_papers/clinsql` (có `openai`, `google-cloud-bigquery`, `sqlglot`). MAC-SQL đã bị loại khỏi thí nghiệm (gửi mẫu giá trị cột ra ngoài) và đã gỡ khỏi repo.
