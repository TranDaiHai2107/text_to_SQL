# Môi trường riêng cho ba source paper

Đã tạo trên Windows/Python 3.12.4 ngày 12/11/2026. Các venv ở `.venv_papers/` được Git ignore; lock package đã cài nằm trong `environment/locks/`. Source gốc vẫn nằm ở `external/` và không bị sửa.

| Môi trường | Dependency đã cài | Smoke check offline |
| --- | --- | --- |
| `.venv_papers/clinsql` | `requirements-clinsql-proprietary.txt`, subset của requirements gốc cho CoT proprietary + rubric scorer. Không cài vLLM/ray/torch/transformers của nhánh open-source. | Native CoT `--help`, scorer `--help`, `pip check` thành công |
| `.venv_papers/mac_sql` | Toàn bộ `external/mac_sql_official/requirements.txt`; giữ `openai==0.28.1`. | Native `run.py --help`, `pip check` thành công |
| `.venv_papers/sde_sql` | Toàn bộ `external/sde_sql_official/requirements.txt`, gồm torch, transformers, `sqlglot==25.6.1`. | Native `gpt_request.py --help`, `pip check` thành công |

Native MAC-SQL README nêu Python 3.9; máy hiện có Python 3.12.4. `--help` và import không chứng minh kết quả inference tương đương. Các lock là snapshot của Python 3.12 trên Windows, không phải dependency lock do tác giả phát hành. Vì `requirements.txt` gốc phần lớn không pin phiên bản, tái tạo môi trường nguyên thời điểm paper sẽ cần thêm metadata/tags từ tác giả.

Tạo lại venv trong PowerShell từ repo root:

```powershell
py -3.12 -m venv .venv_papers/clinsql
py -3.12 -m venv .venv_papers/mac_sql
py -3.12 -m venv .venv_papers/sde_sql
.\.venv_papers\clinsql\Scripts\python.exe -m pip install -r environment/locks/clinsql-py312-win.txt
.\.venv_papers\mac_sql\Scripts\python.exe -m pip install -r environment/locks/mac_sql-py312-win.txt
.\.venv_papers\sde_sql\Scripts\python.exe -m pip install -r environment/locks/sde_sql-py312-win.txt
```

Không dùng native script để chạy CLINSQL test hoặc BigQuery trước khi khóa cấu hình, quyền truy cập và ngân sách. Native SDE còn phụ thuộc file BIRD/Spider ngoài checkout; xem [`docs/PAPER_ALGORITHM_AUDIT.md`](../docs/PAPER_ALGORITHM_AUDIT.md).
