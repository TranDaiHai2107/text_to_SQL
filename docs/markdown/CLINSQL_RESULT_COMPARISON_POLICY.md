# Chính sách kiểm tra kết quả CLINSQL trước pilot

Chính sách này chỉ dùng cho **diagnostic/offline comparison** và báo lỗi dữ liệu. SQL Score và Execution Score chính thức vẫn do evaluator CLINSQL tại commit đã khóa quyết định; không sửa gold SQL, reference CSV, rubric hay logic judge để hợp thức hóa prediction. Inference và retrieval chỉ đọc câu hỏi từ split được phép, tuyệt đối không đọc reference/gold/rubric của test.

- **FLOAT:** so từng giá trị số bằng `abs(a-b) <= 1e-8 + 1e-6 * max(abs(a), abs(b))`. Ghi cả sai khác tuyệt đối và tương đối. Không ép chuỗi lâm sàng, mã ICD hoặc ID thành số. Chốt tolerance trước validation pilot và không thay sau khi nhìn test.
- **Duplicate rows:** giữ số lần xuất hiện của mỗi hàng (multiset). Không dùng phép `set` làm mất duplicate.
- **NULL:** `NULL` khớp duy nhất `NULL`; phân biệt với chuỗi rỗng, số 0, `NaN` và field thiếu. CSV cần xác minh encoding NULL với official scorer trước khi so sánh.
- **Unordered results:** khi câu hỏi không yêu cầu thứ tự, so multiset sau chuẩn hóa kiểu và FLOAT. Khi thứ tự là một phần yêu cầu, kiểm tra thứ tự riêng; không thay SQL gold để tạo tie-break nhân tạo.
- **Kết quả không đầy đủ:** nếu `max_rows` cắt kết quả, không chấm execution từ CSV đó; phải nâng giới hạn được duyệt và chạy lại query bằng adapter read-only, hoặc đánh dấu không thể đánh giá.

## Trường hợp Hard/020

Validation `Disease_Diagnosis_and_Outcomes/hard_level_queries/020` có `NTILE(5) OVER (ORDER BY composite_risk_score ASC)` trong gold SQL. Các hàng cùng `composite_risk_score` có thể được xếp thứ tự khác nhau tại ranh giới quintile, làm kết quả thay đổi giữa lần chạy. Ghi nhận đây là nguy cơ non-determinism, không sửa gold SQL hay reference result. Trước pilot, kiểm tra tie count/boundary bằng truy vấn read-only được duyệt hoặc nhiều lần chạy có giới hạn chi phí; nếu biến động, báo riêng độ nhạy của Execution Score và giữ nguyên scorer chính thức.

Diagnostic không được ghi raw patient rows vào persistent logs và không truyền reference/result rows cho LLM. Chỉ lưu mã lỗi đã loại dữ liệu nhạy cảm, counts, hash/fingerprint và sai khác tổng hợp khi chính sách dữ liệu cho phép.
