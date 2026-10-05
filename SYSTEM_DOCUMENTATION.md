# Tài liệu kỹ thuật hệ thống MIMIC-IV Text-to-SQL

## Phạm vi

Hệ thống nhận câu hỏi y tế tiếng Việt, truy hồi tri thức liên quan, sinh một truy vấn PostgreSQL cho subset MIMIC-IV 31 bảng, kiểm tra truy vấn trước khi chạy và hiển thị kết quả trong Streamlit. Đây là prototype nghiên cứu; độ chính xác cần được đo trên benchmark và không nên được mô tả như một hệ thống loại bỏ hoàn toàn hallucination.

## Thành phần

1. `rewrite_question()` dùng lịch sử hội thoại để biến câu hỏi phụ thuộc ngữ cảnh thành câu độc lập.
2. ICD retrieval kết hợp ánh xạ trực tiếp cho các thuật ngữ Việt phổ biến với semantic retrieval cho trường hợp còn lại.
3. Schema retrieval lọc theo cosine distance và mở rộng các bảng liên kết trực tiếp cần cho JOIN.
4. Example retrieval lấy tối đa ba SQL mẫu. Evaluation dùng collection riêng đã loại trùng gold SQL.
5. Groq `qwen/qwen3.8-27b` sinh SQL với temperature bằng 0 và retry ngắn cho lỗi tạm thời.
6. SQLGlot validator phân tích AST và kiểm tra schema.
7. PostgreSQL thực thi trong transaction read-only với timeout và giới hạn số dòng.
8. Self-correction đưa lỗi validator/runtime về LLM, tối đa theo cấu hình UI.
9. Streamlit hiển thị SQL, bảng và biểu đồ; nội dung động được HTML-escape.

## RAG store

| Collection | Số bản ghi sau build | Vai trò |
|---|---:|---|
| `icd_dictionary` | 10.000 | ICD theo tần suất sử dụng, kèm từ đồng nghĩa Việt cho nhóm bệnh phổ biến |
| `schema_dictionary` | 31 | Mô tả và DDL của 31 bảng |
| `sql_examples` | 101 | Few-shot dùng trong ứng dụng |
| `sql_examples_eval` | 73 | Few-shot benchmark, đã loại 28 SQL trùng gold |

Mỗi collection mới được dựng dưới tên tạm. Script chỉ thay collection đang dùng sau khi số bản ghi khớp `expected_count`. Metadata ghi embedding model và source hash; runtime từ chối collection có model khác cấu hình.

## SQL validator

`sql_validator.py` đọc bảng/cột trực tiếp từ `mimic_schema.json`. Validator:

- Chỉ nhận đúng một `SELECT` hoặc `WITH ... SELECT`.
- Hiểu alias, CTE, subquery, correlated/LATERAL subquery và cột không ghi rõ bảng.
- Từ chối bảng/cột không tồn tại, cột mơ hồ và schema ngoài `public`.
- Từ chối `SELECT INTO`, DDL/DML lồng ghép và các hàm có khả năng đọc file, ngủ, mở kết nối hoặc đổi trạng thái server.
- Bắt buộc JOIN ICD theo `icd_code` và `icd_version`; JOIN eMAR theo `emar_id` và `emar_seq`.

Validator là lớp giảm rủi ro. Quyền database read-only, timeout và row cap vẫn bắt buộc vì kiểm tra tĩnh không thể chứng minh mọi thuộc tính runtime.

## Thực thi PostgreSQL

`run_query()` là cổng thực thi duy nhất cho truy vấn do LLM, ứng dụng và benchmark tạo ra. Hàm này:

1. Gọi validator.
2. Serialize lại AST PostgreSQL để bỏ comment/semicolon thừa.
3. Mở transaction với `postgresql_readonly=True`.
4. Đặt `statement_timeout` và `lock_timeout`.
5. Bọc truy vấn để giới hạn `MAX_QUERY_ROWS`.

Role mặc định là `mimic_reader`. Docker init script đặt `default_transaction_read_only=on` và cấp SELECT. Tài khoản loader được tách qua `DB_LOADER_USER`/`DB_LOADER_PASS`.

## Dữ liệu PostgreSQL

`build_mimic_mini.py` lấy mẫu seed cố định, thêm bệnh nhân để bao phủ mã ICD xuất hiện trong examples/tests và thêm cohort ICU. Script không cắt labevents/chartevents xuống top 50 item nữa. DATE/TIMESTAMP được ép kiểu trước `to_sql`; mỗi bảng được nạp vào staging table rồi đổi tên trong transaction.

Việc thay 31 bảng chưa phải một transaction duy nhất. Nếu loader dừng giữa chừng, các bảng đã đổi tên thuộc lần build mới còn các bảng chưa xử lý thuộc lần cũ. Vì vậy cần chạy lại toàn bộ loader sau sự cố.

## Benchmark

`test_dataset.json` có 180 câu. `evaluate.py`:

- Preflight toàn bộ gold SQL và dừng nếu có lỗi.
- Đo latency từ trước lúc gọi LLM đến sau khi thực thi SQL cho mọi mode.
- So sánh multiset hàng, giữ số lần xuất hiện của dòng trùng, bỏ qua thứ tự hàng và alias cột.
- Không tính gold rỗng vào EX vì hai kết quả rỗng không chứng minh hai truy vấn tương đương.
- Báo VSR, EX, số gold rỗng và metric theo độ khó.

Các mode là `base`, `icd`, `schema`, `examples`, `full`, `full_agentic`. `full_agentic` thêm validator và correction loop; `run_query()` vẫn bảo vệ mọi mode.

## Quyền riêng tư

Với `SEND_RESULTS_TO_LLM=false`, các hàng dữ liệu kết quả không rời máy để phục vụ SQL-to-text. UI dùng diễn giải cục bộ ngắn và vẫn hiển thị DataFrame. Nếu bật tùy chọn này, tối đa 20 dòng được gửi tới Groq; người vận hành phải tự kiểm tra quyền sử dụng dữ liệu và chính sách của nhà cung cấp.

## Giới hạn còn lại

- Query rewriting và self-correction phụ thuộc LLM, nên không hoàn toàn xác định.
- ICD direct map chỉ bao phủ một số thuật ngữ Việt phổ biến; các bệnh khác phụ thuộc embedding.
- Subset 500 bệnh nhân không đại diện cho toàn bộ MIMIC-IV; một số gold query có thể trả rỗng.
- Execution equivalence không phát hiện mọi truy vấn sai khi kết quả tình cờ trùng nhau.
- Chưa có semantic parser chuyên cho đơn vị, khoảng thời gian và phủ định y khoa.

## Vận hành

Xem [README.md](README.md) và [HUONG_DAN_CHAY.md](HUONG_DAN_CHAY.md). Các lệnh kiểm tra tối thiểu:

```powershell
python -m unittest discover -s tests -v
python build_vector_db.py
python evaluate.py --quick --modes full full_agentic
python -m streamlit run app.py
```
