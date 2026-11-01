# Audit độc lập số liệu Text-to-SQL — 01/11/2026

Kết luận: **PASS; không phát hiện sai số hoặc lỗi mẫu số trong số liệu đã bàn giao.**

Audit sử dụng SQLite read-only và bộ chuẩn hóa/chấm độc lập chỉ bằng stdlib; không import production comparison hoặc adapter scorer. Đã replay đủ 4 × 1.167 prediction, khớp từng nhãn chấm lịch sử; 147 file khóa và database không đổi. Không gọi API.

- **V5**: RS10 74.892888; EX 92.291221%; VSR 75.664096%; correct 1084, wrong 21, false-abstention 62; precision 97.621744%.
- **Vanna**: RS10 -58.097686; EX 85.867238%; VSR 82.862039%; correct 992, wrong 167, false-abstention 8; precision 82.765738%.
- **Vanna_GEF**: RS10 -12.082262; EX 85.867238%; VSR 78.577549%; correct 1009, wrong 115, false-abstention 43; precision 87.459106%.
- **ProbGate_paper_cache**: RS10 74.207369; EX 77.730193%; VSR 62.982005%; correct 956, wrong 9, false-abstention 202; precision 98.775510%.

RS0/RS5/RS10/RSN, EX, VSR, coverage, precision và false-answer counts đều khớp JSON bàn giao. EX dùng 934 câu answerable; VSR và RS dùng toàn bộ 1.167. Hai empty-string SQL của Vanna vẫn bị tính lỗi thực thi, không bị xem là từ chối đúng.

Đã đối chiếu [PDF chính thức, Table 2, trang PDF 6](https://aclanthology.org/2024.clinicalnlp-1.65.pdf): cấu hình cuối GPT-3.5-turbo FT + ProbGate(t=425) + GEF có RS 81.92 / 78.06 / 74.21 / −818.08. EX/VSR paper là tính bổ sung từ cache, không phải cột công bố. Config Vanna, generation protocol V3/V5 và success events Vanna xác nhận DeepSeek Flash; không trộn kết quả OpenAI/partial run.

Không phát hiện claim vượt phạm vi trong README/báo cáo: đã nêu test-informed development, khác model/knowledge/ngân sách, replay paper, host thay vì fresh Docker, và không có điểm SQL→English của paper. Chênh RS10 khoảng +0,69 quan sát không chứng minh ưu thế nghiên cứu độc lập.

Giới hạn audit: xác nhận số đo trên snapshot hiện tại; không xác nhận clinical correctness của gold SQL, độ tổng quát hóa hay backbone fairness. Không có lỗi cần sửa trong phạm vi audit này.
