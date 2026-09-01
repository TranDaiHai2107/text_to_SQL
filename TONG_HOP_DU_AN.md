# TỔNG HỢP VÀ GIẢI THÍCH DỰ ÁN TEXT-TO-SQL Y TẾ (MIMIC-IV)

Tài liệu này tổng hợp lại toàn bộ mục tiêu, tiến độ những gì đã làm được trong Phase 1, cũng như công việc đang tiến hành để giúp bạn có cái nhìn tổng quan nhất về dự án.

---

## 1. Mục tiêu hiện tại của đồ án là gì?

Mục tiêu cốt lõi của chúng ta là xây dựng một **Hệ thống Text-to-SQL chuyên biệt cho dữ liệu y tế (MIMIC-IV)**. 
- Hệ thống này giúp bác sĩ và các nhà nghiên cứu lâm sàng có thể đặt câu hỏi bằng **tiếng Việt** (ngôn ngữ tự nhiên).
- Trí tuệ nhân tạo (AI) sẽ tự động sinh ra các câu lệnh truy vấn SQL chính xác để trích xuất dữ liệu từ bệnh viện, thay vì họ phải tự viết code SQL phức tạp.
- Để đạt được độ chính xác cao nhất (tránh AI sinh bậy), hệ thống không chỉ dùng Prompt đơn thuần mà áp dụng kiến trúc **RAG 3 tầng (RAG Đa tầng)** và cơ chế **Agentic Self-Correction** (AI tự kiểm tra kết quả từ Database và tự sửa lỗi nếu sinh sai SQL).

---

## 2. Tổng hợp những gì đã làm được (Giai đoạn 1 - Xây dựng nền tảng)

Chúng ta đã giải quyết thành công các vấn đề kỹ thuật nền tảng (Foundation) để chuẩn bị cho các bước đánh giá chuyên sâu. Cụ thể:

### Task 1.2: Nâng cấp Multilingual Embedding (Hỗ trợ tiếng Việt)
- **Vấn đề trước đây:** Khi bác sĩ hỏi bằng tiếng Việt, hệ thống dùng model embedding tiếng Anh nên không thể tìm (match) ra đúng thuật ngữ bệnh học và bảng tương ứng, dẫn đến kết quả sai.
- **Giải pháp đã làm:** Đổi sang dùng mô hình nhúng đa ngôn ngữ `paraphrase-multilingual-MiniLM-L12-v2`. Mô hình này hỗ trợ tiếng Việt cực mượt, ánh xạ rất tốt giữa thuật ngữ y khoa tiếng Việt của người dùng và mã bệnh ICD tiếng Anh trong Database. Nó cũng đủ nhẹ để chạy mượt mà trên laptop cá nhân (VRAM ~4GB).

### Task 1.4: Xây dựng Schema-Aware SQL Validator (Chặn lỗi Ảo giác)
- **Vấn đề trước đây:** Các mô hình ngôn ngữ (LLM) thường bị bệnh "ảo giác", tự bịa ra tên bảng hoặc tên cột không có thật trong Database.
- **Giải pháp đã làm:** Xây dựng module `Schema-Aware SQL Validator`. Module này đóng vai trò như một màng lọc, tự động phân tích (parse) câu lệnh SQL vừa sinh ra để xem tên bảng/cột có thật sự tồn tại không. Nếu phát hiện lỗi (ví dụ: dùng sai cột), nó sẽ lập tức chặn lệnh gửi tới DB và trả về câu prompt bắt LLM tự sửa (Self-correction). Việc này giúp hệ thống hoạt động cực kỳ ổn định.

### Task 1.3: Mở rộng bộ dữ liệu kiểm tra (Test Dataset lên 100 câu)
- **Vấn đề trước đây:** Chỉ có 30 câu hỏi để test thì không đủ độ tin cậy trong nghiên cứu khoa học.
- **Giải pháp đã làm:** Tạo ra bộ 100 câu hỏi kèm đáp án SQL chuẩn xác (Gold SQL), phủ kín toàn bộ 12 bảng của cơ sở dữ liệu MIMIC-IV. Đồng thời phân loại rõ ràng 4 mức độ: Easy (21%), Medium (40%), Hard (25%), Complex (14%).

---

## 3. Hiện tại đang làm gì & Ý tưởng ra sao?

### Đang làm gì (Task 1.1)
- Hiện tại, tụi mình đang tiến hành chạy đo lường **Baseline V1** bằng script `evaluate.py` trên tập 100 câu hỏi mới tạo.
- Mục đích là để lấy được một "con số mốc" (benchmark) về **Valid SQL Rate (Tỷ lệ SQL chạy không lỗi)** và **Execution Accuracy (Tỷ lệ kết quả truy vấn chính xác)**.

### Ý tưởng thực hiện (Ablation Study)
- Hệ thống sẽ chạy test thử qua 5 chế độ (modes) khác nhau. Ví dụ: Chế độ chỉ có LLM, chế độ có LLM + RAG từ điển ICD, chế độ RAG đầy đủ...
- Kết quả thu được sẽ cho thấy mức độ đóng góp (bao nhiêu %) của từng kỹ thuật (RAG 3 tầng) vào sự thành công của hệ thống so với việc chỉ dùng AI thông thường.

---

## 4. Cần phải làm gì tiếp theo và làm ra sao?

Tiến độ hiện tại đang bị dừng ở việc **không kết nối được với PostgreSQL Database** (lỗi "Connection refused"). Đây là các bước chúng ta cần xử lý ngay:

- **Bước 1 (Bật Database):** Mở phần mềm **Docker Desktop** trên máy tính lên, đảm bảo trạng thái của container `mimic-postgres` đang là "Running".
- **Bước 2 (Chạy Script Đánh Giá):** Sau khi có DB, mở Terminal (tại folder `official`) và chạy câu lệnh sau để AI làm bài test 100 câu:
  ```bash
  python evaluate.py --mode full --output results/baseline_v1.json
  ```
- **Bước 3 (Test Thực Tế Trên Web):** Chạy lệnh sau để mở giao diện Chatbot, vừa có thể nhập câu hỏi test thử như một người dùng thực tế, vừa có thể xem được bảng thống kê kết quả chạy ở Bước 2.
  ```bash
  python -m streamlit run app.py
  ```

> Đọc thêm file `HUONG_DAN_CHAY.md` để biết chi tiết cách setup từng lệnh nếu chưa rõ nhé!
