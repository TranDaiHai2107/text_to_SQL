# Audit độc lập bộ chấm tiếng Anh

Lần audit: post_fix_provenance_verified. Không API; 147 file đóng băng không đổi.

Kiểm tra DP độc lập trên 961 cặp chuỗi; các case số sai, dấu âm, số thập phân, phủ định, duplicate, column order, >100 rows, NULL/empty/refusal/errors và JSON lỗi đã chạy.

Không còn finding tái hiện được trong phạm vi script này.

Hai lỗi input integrity đã tái hiện trước khi parent sửa: JSON mapping có ID trùng bị ghi đè; reference controlled text có thể trái result_rows. Cả hai hiện được kiểm tra lại và từ chối. Các lỗi này không làm thay đổi7454nhãn đã audit hoặc kết quả Text-to-SQL cũ.

Grammar hiện yêu cầu đúng spelling numeric chuẩn và sorted serialization; prose tương đương ngoài grammar bị factEM=0. Đây là giới hạn định dạng đã khai báo, không phải validator ngữ nghĩa tự do.

Self-check dữ liệu không bị gán là kết quả model. Bản giao trước có51testfunction+5subtest=56JUnitcase; hiện tại61testfunction+5subtest=66JUnitcase. Số56trong run cũ chỉ là lịch sử.

Hai finding trước sửa được ghi nhận bằng probe Python tương tác, không phải lần chạy script trên snapshot cũ. Tất cả run script đã lưu đều chạy sau khi parent sửa; JSON giữ original phase label và ghi rõ hash/status sau sửa. Hash code cũ lấy từ artifact bàn giao trước, không phải một formal scripted pre-fix rerun.
