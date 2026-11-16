# Kiến trúc và trạng thái

## Đích kiến trúc và code hiện có

Đích chung là MIMIC-IV v3.1 trên BigQuery. `src/ehrqa/app.py` và `rag_engine.py` hiện vẫn chạy trên PostgreSQL/MIMIC Mini; cần chuyển adapter trước khi coi ứng dụng đã dùng BigQuery. Core `src/ehrqa/agentic/` thực hiện rewrite, retrieval, schema linking, phân rã yêu cầu, sinh SQL, kiểm tra/thực thi, sửa lỗi, semantic verification và chọn ứng viên. Code ứng dụng và bước diễn giải tiếng Việt được giữ nguyên.

## Nhánh nghiên cứu CLINSQL

`src/ehrqa/clinsql/` có loader chỉ đưa câu hỏi tiếng Anh vào inference, chia validation cố định, interface DB/evaluator, BigQuery adapter mặc định chặn thực thi dữ liệu, khung CLINSQL CoT và cấu hình BigQuery/English cho hệ thống đề xuất. Evaluator chính thức chưa được nối; chưa có kết quả model hay BigQuery.

Mục tiêu là đối chiếu hệ thống đề xuất với CLINSQL CoT, MAC-SQL và SDE-SQL trên cùng MIMIC-IV v3.1/BigQuery bằng CLINSQL SQL Score và Execution Score. MAC-SQL/SDE-SQL chỉ tích hợp sau khi pipeline và chi phí được kiểm chứng. Giới hạn probe evidence có thể khiến SDE-SQL chỉ là bản adapted/restricted; phải báo blocker nếu không thể tái hiện trung thực.

Điều kiện chạy và khóa test nằm trong [EXPERIMENT_PROTOCOL.md](EXPERIMENT_PROTOCOL.md); mọi thay đổi baseline ghi tại [BASELINE_ADAPTATION.md](BASELINE_ADAPTATION.md).
