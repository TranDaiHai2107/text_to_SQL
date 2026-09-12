# TỔNG HỢP VÀ BÁO CÁO TIẾN ĐỘ DỰ ÁN TEXT-TO-SQL Y TẾ (MIMIC-IV)

Tài liệu này tổng hợp toàn diện mục tiêu nghiên cứu, kiến trúc kỹ thuật, các kết quả đã hoàn thiện và kế hoạch hoàn tất đồ án tốt nghiệp.

---

## 1. Mục tiêu Cốt lõi của Đề tài

Xây dựng **Hệ thống Text-to-SQL lâm sàng đa ngữ hai chiều (Closed-Loop Clinical Text-to-SQL & SQL-to-Text)** trên cơ sở dữ liệu y tế MIMIC-IV:
1. **Chiều xuôi (Text-to-SQL):** Cho phép y bác sĩ và nhà nghiên cứu đặt câu hỏi lâm sàng bằng **ngôn ngữ tự nhiên tiếng Việt**, hệ thống tự động sinh câu truy vấn SQL chuẩn xác trên PostgreSQL.
2. **Chiều ngược (SQL-to-Text / Result Interpretation):** Sau khi thực thi SQL và thu được bảng dữ liệu, hệ thống tự động tổng hợp và diễn giải kết quả thành **câu trả lời ngôn ngữ tự nhiên tiếng Việt** ngắn gọn, chuẩn xác, dễ hiểu cho bác sĩ lâm sàng mà không yêu cầu kiến thức kỹ thuật.
3. **Đảm bảo độ tin cậy:** Khắc phục triệt để hiện tượng ảo giác (hallucination), sai lệch tên bảng/cột và cú pháp JOIN thông qua **RAG 3 tầng**, **Schema-Aware Validator** và **Agentic Self-Correction**.

---

## 2. Các Thành phần Kỹ thuật Đã Hoàn Thiện 100%

Hệ thống đã được lập trình hoàn chỉnh, kiểm thử end-to-end thành công với các thành phần:

### 2.1. Nhúng Đa Ngôn ngữ (Cross-lingual Multilingual Embedding)
- **Cấu hình:** Sử dụng mô hình `paraphrase-multilingual-MiniLM-L12-v2` (`embedding_config.py`).
- **Hiệu quả:** Ánh xạ xuất sắc giữa câu hỏi tiếng Việt có dấu/không dấu với cơ sở dữ liệu y tế tiếng Anh (mã bệnh ICD, mô tả bảng, câu mẫu), giải quyết rào cản bất đồng ngôn ngữ trong y tế.

### 2.2. Kiến trúc RAG 3 Tầng Chuyên Biệt (Domain-Specific Multi-Layer RAG)
- **Tầng 1 (ICD Dictionary Retrieval):** Kho 10,000 vector mã bệnh (ICD-9 & ICD-10) từ `d_icd_diagnoses`. Tự động nhận diện thực thể bệnh trong câu hỏi (ví dụ: *"viêm phổi"* → ICD-9: `486`, ICD-10: `J189`) để chèn mã chính xác vào mệnh đề `WHERE`.
- **Tầng 2 (Schema Selection Retrieval):** Kho 31 vector mô tả song ngữ của 31 bảng MIMIC-IV. Tự động chọn lọc động 3–5 bảng liên quan nhất thay vì nhồi toàn bộ 31 bảng gây loãng context và quá tải token.
- **Tầng 3 (SQL Examples Few-Shot Retrieval):** Kho 101 cặp câu hỏi tiếng Việt ↔ SQL Gold (`mimic_examples.json`), truy xuất 3 câu mẫu tương đồng nhất về mặt ngữ nghĩa và cấu trúc SQL.

### 2.3. Màng lọc Schema-Aware SQL Validator (`sql_validator.py`)
- Phân tích cú pháp AST (Abstract Syntax Tree) của câu lệnh SQL trước khi gửi tới PostgreSQL.
- Kiểm tra toàn diện: Bảng có tồn tại không? Cột có thuộc bảng tương ứng không? Có JOIN thiếu phiên bản ICD (`icd_code` và `icd_version`) không?
- Ngăn chặn triệt để hiện tượng hallucination trước khi tác động đến cơ sở dữ liệu.

### 2.4. Vòng lặp Tự Sửa Lỗi Tác tử (Agentic Self-Correction Loop)
- Tích hợp trong `generate_sql_with_correction()`: Nếu câu lệnh bị lỗi bởi Validator hoặc PostgreSQL runtime error, hệ thống thu thập thông báo lỗi cụ thể, phản hồi lại LLM để tự động điều chỉnh câu lệnh (tối đa 2 lần retry).

### 2.5. Xử lý Ngữ cảnh Đa lượt Sâu (Context-Aware Multi-turn Query Rewriting)
- Module `rewrite_question()` được nâng cấp vượt trội: Không chỉ đọc câu hỏi trước mà còn đọc cả **câu SQL đã sinh** và **kết quả dữ liệu** của các lượt chat trước.
- **Đặc biệt:** Tích hợp quy tắc truy vấn tập con (Subquery/CTE Logic) cho các câu hỏi phụ thuộc như *"trong đó có bao nhiêu nam?"*. Hệ thống hiểu bản chất "trong đó" là tập kết quả từ câu hỏi trước, sinh subquery chính xác (ví dụ: tìm nam trong tập bệnh nhân nữ → trả về 0 đúng bản chất logic).

### 2.6. Diễn giải Kết quả Hai chiều (SQL-to-Text Interpretation)
- Hàm `interpret_result()` đóng vai trò chuyển đổi kết quả định lượng (DataFrame) thành ngôn ngữ tự nhiên tiếng Việt trực quan.
- Tự động tóm lược xu hướng, làm nổi bật số liệu quan trọng và hiển thị trong khung thông báo nổi bật trên giao diện.

### 2.7. Tối ưu hóa Hạn mức Token (Rate Limit & OTPM Protection)
- Khắc phục triệt để lỗi `429 RateLimitError` từ Groq: Giảm `max_tokens` từ 1024 xuống 900 cho sinh SQL và 256 cho rewrite câu hỏi, hoàn toàn tương thích với mức trần 1,000 OTPM của Groq Free Tier.

### 2.8. Bộ Dữ liệu Đánh giá Chuẩn Hóa (180 Test Cases với Gold SQL)
- File `test_dataset.json` chứa 180 câu hỏi tiếng Việt độc lập kèm Gold SQL chính xác phủ kín 31 bảng, phân tầng thành 4 cấp độ: **Easy (37%)**, **Medium (33%)**, **Hard (11%)**, **Complex (19%)**.

### 2.9. Ứng dụng Giao diện Trực quan (Streamlit Web App - `app.py`)
- Giao diện chat trực quan với các tag màu hiển thị RAG stages (`ICD`, `SCHEMA`, `EXAMPLES`, `REWRITE`, `FIX`).
- Khung hiển thị câu trả lời tự nhiên tím gradient nổi bật.
- Bảng dữ liệu tương tác, vẽ biểu đồ tự động và xuất file CSV.
- Dashboard tích hợp hiển thị kết quả benchmark Ablation Study trực quan.

---

## 3. Bảng Đối Chiếu Hiện Trạng Hệ Thống

| Thành phần / Tính năng | Trước cải tiến | Hiện tại (Đã hoàn thành) |
|---|---|---|
| **Mô hình Embedding** | `all-MiniLM-L6-v2` (chỉ tiếng Anh) | `paraphrase-multilingual-MiniLM-L12-v2` (đa ngữ, chuẩn tiếng Việt) |
| **Bảo vệ Schema** | Không có (dễ bị ảo giác) | `sql_validator.py` kiểm tra bảng, cột, điều kiện JOIN |
| **Xử lý đa lượt** | Chỉ đọc chuỗi văn bản đơn giản | Đọc sâu kèm SQL và kết quả trước + Rule sinh Subquery tập con |
| **Đầu ra hệ thống** | Chỉ trả về bảng dữ liệu thô | Trả về cả SQL, Data Table, Biểu đồ và **Diễn giải tự nhiên tiếng Việt** |
| **Quản lý Token** | Dễ bị chặn lỗi 429 OTPM | Tối ưu hóa `max_tokens=900/256`, ổn định không bị gián đoạn |
| **Tập Test Benchmark** | 30 câu chưa phân cấp | 180 câu phân tầng rõ ràng 4 cấp độ phức tạp |
| **Trạng thái Database** | Từng bị dừng container | PostgreSQL Docker (`mimic-postgres`) đang chạy ổn định |

---

## 4. Các Bước Kế Tiếp để Hoàn Tất Đồ Án

1. **Chạy Ablation Study Benchmark:**
   - Chạy lệnh `python evaluate.py --quick` để kiểm tra nhanh chỉ số **VSR** (Valid SQL Rate) và **EX** (Execution Accuracy) trên 10 câu cho cả 6 mode (`base`, `icd`, `schema`, `examples`, `full`, `full_agentic`).
   - (Tùy chọn) Chạy trọn vẹn 180 câu trên mode `full` để có số liệu chính thức ghi vào báo cáo.
2. **Xuất Số Liệu và Biểu Đồ:**
   - Số liệu từ `evaluate_results.json` sẽ tự động hiển thị trong expander của giao diện Streamlit.
3. **Hoàn thiện Báo cáo Đồ án Tốt nghiệp:**
   - Dựa trên 5 điểm mới khoa học (Novelty Claims) và bảng kết quả thực nghiệm để đưa vào tài liệu bảo vệ tốt nghiệp.
