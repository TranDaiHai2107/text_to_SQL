# HƯỚNG DẪN CÀI ĐẶT VÀ VẬN HÀNH HỆ THỐNG MIMIC-IV TEXT-TO-SQL

Tài liệu này hướng dẫn chi tiết cách cài đặt, cấu hình và vận hành hệ thống Text-to-SQL y tế (MIMIC-IV) với kiến trúc RAG đa tầng, Agentic Self-Correction và Diễn giải kết quả hai chiều (SQL-to-Text).

---

## 1. Yêu Cầu Hệ Thống (Prerequisites)
- **Hệ điều hành:** Windows / Linux / macOS.
- **Python:** Phiên bản 3.10 trở lên (khuyến nghị Python 3.11 hoặc 3.12).
- **Docker Desktop:** Bắt buộc để khởi chạy PostgreSQL chứa dữ liệu MIMIC-IV. (Đảm bảo Docker Desktop đang ở trạng thái **Running**).
- **Phần cứng:** Tối thiểu 8GB RAM (khuyến nghị 16GB RAM).
- **Tài khoản Groq:** Đăng ký miễn phí tại [https://console.groq.com](https://console.groq.com) để nhận `GROQ_API_KEY`.

---

## 2. Cài Đặt Môi Trường Python

Mở PowerShell hoặc Command Prompt tại thư mục gốc của dự án (`d:\Github\text_to_SQL`) và chạy lệnh cài đặt:

```bash
pip install groq chromadb sqlalchemy psycopg2-binary pandas streamlit python-dotenv sentence-transformers sqlparse
```

---

## 3. Cấu Hình Biến Môi Trường (.env)

Tạo hoặc kiểm tra file `.env` tại thư mục gốc của dự án:

```env
GROQ_API_KEY=gsk_your_actual_groq_api_key_here
```

> **Lưu ý về Rate Limit của Groq Free Tier:**
> - Hạn mức miễn phí của Groq giới hạn **1,000 Output Tokens Per Minute (OTPM)** và **200,000 Tokens Per Day (TPD)**.
> - Hệ thống đã được tối ưu hóa sẵn trong `rag_engine.py` với `max_tokens=900` khi sinh SQL và `max_tokens=256` khi viết lại câu hỏi để chống lỗi `429 RateLimitError`.

---

## 4. Khởi Động Cơ Sở Dữ Liệu (PostgreSQL trên Docker)

### 4.1. Khởi tạo container lần đầu (Nếu chưa tạo bao giờ):
```bash
docker run -d --name mimic-postgres -e POSTGRES_PASSWORD=password123 -e POSTGRES_DB=mimiciv -p 5432:5432 postgres:15
```

### 4.2. Khởi động lại container (Các lần sử dụng tiếp theo):
Mỗi khi khởi động lại máy hoặc container đang bị dừng:
```bash
docker start mimic-postgres
```

### 4.3. Kiểm tra kết nối Database:
```bash
python -c "from rag_engine import engine; print('DB connected:', engine.connect().execute(__import__('sqlalchemy').text('SELECT 1')).scalar())"
```
*(Nếu terminal in ra `DB connected: 1` tức là cơ sở dữ liệu đã sẵn sàng).*

---

## 5. Build Dữ Liệu & Vector Database (Chỉ chạy 1 lần duy nhất lúc khởi tạo)

Nếu đã build sẵn dữ liệu trong thư mục `mimic_chroma_db/` thì có thể bỏ qua bước này:

1. **Nạp 12 bảng dữ liệu MIMIC-IV vào PostgreSQL**:
   ```bash
   python build_mimic_mini.py
   ```
2. **Xây dựng ChromaDB Vector Database** (sử dụng multilingual embedding `paraphrase-multilingual-MiniLM-L12-v2`):
   ```bash
   python build_vector_db.py
   ```

---

## 6. Khởi Chạy Ứng Dụng Giao Diện Web (Streamlit UI)

Chạy lệnh sau tại thư mục gốc:
```bash
python -m streamlit run app.py
```
Hệ thống sẽ tự động mở trình duyệt tại địa chỉ: `http://localhost:8501`.

### Các tính năng nổi bật trên giao diện:
1. **Hỏi đáp y khoa bằng tiếng Việt**: Chuyển câu hỏi lâm sàng sang câu lệnh SQL chuẩn xác.
2. **Diễn giải tự nhiên hai chiều (SQL-to-Text)**: Hiển thị câu trả lời y tế thân thiện (khung gradient màu tím) trực tiếp cho bác sĩ.
3. **Multi-turn Context Aware**: Hiểu rõ ngữ cảnh đối thoại liên tiếp (kế thừa câu hỏi, câu SQL và kết quả trước đó để lọc tập con chính xác).
4. **Agentic Self-Correction Tracker**: Hiển thị trực quan quá trình AI tự phát hiện lỗi cú pháp/schema và tự động sửa câu lệnh.
5. **Visual RAG Inspector**: Xem chi tiết mã ICD, cấu trúc bảng DDL và các câu SQL mẫu tương tự được truy xuất từ Vector DB.
6. **Bảng dữ liệu & Biểu đồ tự động**: Tự động vẽ biểu đồ cột/đường và cho phép xuất file `.csv`.

---

## 7. Chạy Đánh Giá Ablation Study (Đo lường độ chính xác)

Hệ thống cung cấp script `evaluate.py` để đo lường 2 chỉ số học thuật cốt lõi:
- **VSR (Valid SQL Rate)**: Tỷ lệ câu SQL sinh ra thực thi thành công không lỗi syntax/runtime.
- **EX (Execution Accuracy)**: Tỷ lệ câu SQL cho ra bảng dữ liệu kết quả trùng khớp 100% với Gold SQL chuẩn.

### 7.1. Chạy đánh giá nhanh (Quick Mode - Khuyến nghị cho Groq Free Tier):
Chạy trên 10 câu hỏi mẫu tiêu biểu của 5 chế độ ablation (`base`, `icd`, `schema`, `examples`, `full`) để kiểm tra nhanh mà không sợ hết quota:
```bash
python evaluate.py --quick
```

### 7.2. Chạy đánh giá toàn diện trên toàn bộ 100 câu:
```bash
# Chạy đầy đủ 5 mode ablation (cần tài khoản Groq đủ quota hoặc key trả phí)
python evaluate.py

# Hoặc chỉ chạy riêng mode đề xuất (full mode RAG 3 tầng)
python evaluate.py --modes full
```

Kết quả sẽ tự động lưu vào file `evaluate_results.json` và được trực quan hóa thành bảng số liệu kèm biểu đồ so sánh ở cuối trang web Streamlit (`app.py`).
