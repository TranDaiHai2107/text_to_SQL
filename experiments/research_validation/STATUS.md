# Trạng thái xác nhận nghiên cứu — 29/10/2026

Đã khóa V5 và 147 file nguồn/phụ thuộc/database/scorer/output lịch sử bằng SHA-256, giữ RS10=74,8929. Code ứng dụng và các phiên bản V3/V4/V5/Vanna cũ không bị sửa. Giao thức và implementation xác nhận mới cũng đã khóa hash nội bộ; chưa công bố preregistration ra bên ngoài.

## Đã hoàn thành

- Thiết kế bảy arm từ ba gia đình generation, cùng backbone, knowledge và trần generation; tách Vanna native khỏi Vanna augmented.
- Runner inference cho đủ ba replicate, checkpoint từng gia đình/câu hỏi, không đọc nhãn để đưa vào prompt và không pad lỗi API thành null.
- Intake dữ liệu kiểm tra nguồn nhãn/cluster, trùng ID/câu hỏi, thay literal số và near-duplicate. Không tự coi việc chạy SQL thành công là xác nhận ngữ nghĩa.
- Scorer tách riêng, yêu cầu mọi replicate hoàn thành trước khi chấm; paired cluster bootstrap/randomization, Holm cho secondary, báo cả kết quả bất lợi và token thực tế.
- Chạy ablation offline trên 1.167 câu test cũ: raw consensus 71,21 → V4 normalization 73,09 → compiler V5 74,89. Không phải holdout độc lập.
- 17 unit test và smoke tích hợp index thật đã qua. V5 gốc vẫn khớp lock.
- Tải cách ly hai test công bố của EHRSQL MIMIC-III/eICU, pin commit và hash. Đã audit trùng câu hỏi; chưa sinh prediction/chấm model trên các tập mới.

## Chưa hoàn thành và lý do

Chưa chạy đối chứng mới hoặc công bố kết quả confirmatory. Ba split EHRSQL 2024 đã tiếp xúc trong knowledge/phát triển/đánh giá. MIMIC-III/eICU có gold chính thức nhưng khác schema/clock, có overlap và chưa có adapter cross-database được xác nhận; không thể áp dụng trực tiếp protocol MIMIC-IV đã khóa.

Điều kiện tiếp theo là có tập câu hỏi–SQL/null mới được kiểm định cho đúng database hiện tại, hoặc triển khai và đăng ký riêng đánh giá chuyển miền với adapter được kiểm tra. Không tự tạo nhãn rồi gọi đó là benchmark chính thống. Chưa cần người chấm lại nếu dùng đúng gold chính thức; vẫn cần giải quyết tương thích schema và overlap.

**Chi phí model mới trong lượt công việc này: 0 API call.** Không thay quota/gói, không tự mua credit. Rerun matched inference chỉ hợp lý sau khi có dữ liệu đủ điều kiện; không tiêu credit để chạy lại test đã dùng nhằm lấy thêm điểm.

Tệp chính: `README.md`, `protocol.json`, `V5_LOCK.json`, `PROTOCOL_LOCK.json`, `READINESS.json`, `EXTERNAL_DATA_AUDIT.json`, `runs/exploratory_20261029/ablation.json`.
