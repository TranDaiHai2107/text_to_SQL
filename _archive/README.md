# Bằng chứng và kết quả lịch sử

Cập nhật 08/11/2026. Đã xóa cây nghiên cứu/dataset/download M3 và các file Python/PowerShell thí nghiệm cũ khỏi `20261106/workspace/experiments`.

`locked_source_evidence.zip` giữ byte gốc code đã xóa để kiểm tra nguồn gốc. V6 không import/chạy code trong ZIP. Runtime V6 đã tách sang `experiments/ours_improved_v6/runtime`.

Giữ cache sinh SQL, dữ liệu run, lock và báo cáo Vanna/OpenAI/DeepSeek phục vụ tái lập và so sánh. V6 vẫn đọc dữ liệu cache lịch sử; không được xóa toàn bộ archive. `project_layout.verify_historical()` kiểm tra 147 hash từ file dữ liệu hoặc code nguồn trong ZIP. Các lock cũ vẫn là lock lịch sử, không phải hash code mới.
