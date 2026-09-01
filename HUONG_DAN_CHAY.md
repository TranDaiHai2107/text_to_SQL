# HƯỚNG DẪN CÀI ĐẶT VÀ CHẠY HỆ THỐNG MIMIC-IV TEXT-TO-SQL

Tài liệu này hướng dẫn cách setup và chạy dự án Text-to-SQL y tế dựa trên dữ liệu MIMIC-IV. 

## 1. Yêu Cầu Hệ Thống (Prerequisites)
- **Python:** Phiên bản 3.10 trở lên.
- **Docker Desktop:** Cần thiết để chạy database PostgreSQL. (Hãy đảm bảo Docker Desktop đã được bật và đang chạy trên máy).
- **RAM:** Tối thiểu 8GB (khuyến nghị 16GB).
- **Tài khoản Groq:** Đăng ký miễn phí tại [https://console.groq.com](https://console.groq.com) để lấy API Key.

## 2. Cài Đặt Môi Trường
Mở terminal/command prompt tại thư mục `official/` và chạy lệnh sau để cài đặt các thư viện cần thiết:
```bash
pip install groq chromadb sqlalchemy psycopg2-binary pandas streamlit python-dotenv sentence-transformers
```

## 3. Cấu Hình API Key
Tạo một file có tên là `.env` nằm trong cùng thư mục `official/` (ngang hàng với `app.py`) và thêm nội dung sau:
```env
GROQ_API_KEY=gsk_xxxxxxxxxxxxxxxxxxxxxxxx
```
*(Thay `gsk_xxxxxxxxxxxxxxxxxxxxxxxx` bằng API key thực tế lấy từ Groq)*

## 4. Khởi Động Database (PostgreSQL)
Mở terminal và chạy lệnh Docker sau để tạo container cơ sở dữ liệu:
```bash
docker run -d --name mimic-postgres -e POSTGRES_PASSWORD=password123 -e POSTGRES_DB=mimiciv -p 5432:5432 postgres:15
```
**Lưu ý quan trọng:** Mỗi khi khởi động lại máy, bạn cần mở Docker Desktop và đảm bảo container `mimic-postgres` đang ở trạng thái **Running**.

## 5. Build Dữ Liệu (Chỉ chạy 1 lần duy nhất lúc mới setup)
Chạy lần lượt các lệnh sau:
1. **Nạp dữ liệu MIMIC-IV vào PostgreSQL** (sẽ tốn khoảng 10 phút):
```bash
python build_mimic_mini.py
```
2. **Xây dựng Vector Database** (ChromaDB sẽ tải mô hình embedding đa ngôn ngữ về và tạo db):
```bash
python build_vector_db.py
```

## 6. Khởi Chạy Ứng Dụng (Chạy hằng ngày)
Sau khi đã hoàn tất các bước trên, bạn có thể chạy ứng dụng web Streamlit bằng lệnh:
```bash
python -m streamlit run app.py
```
Trình duyệt sẽ tự động mở trang web tại địa chỉ `http://localhost:8501`.

## 7. Chạy Kịch Bản Đánh Giá (Evaluation / Baseline)
Để đo lường độ chính xác và lấy baseline cho 100 câu hỏi test, bạn có thể chạy script đánh giá:
```bash
# Chạy đánh giá toàn bộ các mô hình (Full mode)
python evaluate.py --mode full --output results/baseline_v1.json

# Chạy test nhanh 10 câu
python evaluate.py --quick
```
Kết quả đánh giá sẽ được lưu lại dưới dạng file JSON và có thể xem trực tiếp phần thống kê ở cuối trang web ứng dụng Streamlit.
