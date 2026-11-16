# Hệ thống MIMIC-IV và hướng nghiên cứu CLINSQL

## Định hướng triển khai

- **Đích chung:** MIMIC-IV v3.1 trên BigQuery cho hệ thống đề xuất và đánh giá CLINSQL 2026.
- **Quyết định kiến trúc cuối cùng:** cả hệ thống tiếng Việt và các hệ thống thực nghiệm CLINSQL sẽ dùng BigQuery. Migration ứng dụng tiếng Việt được hoãn; không sửa code tiếng Việt trong giai đoạn metadata integration.
- **Trạng thái code:** nhánh BigQuery/English tại `src/ehrqa/clinsql/` chạy được bằng mock. Đường CLI PostgreSQL/MIMIC Mini đã ngừng kích hoạt; schema Mini và script dựng Mini đã xóa. Source ứng dụng tiếng Việt cũ còn lưu để tham khảo nhưng không là runtime benchmark. Chưa kết nối BigQuery/LLM thật hoặc có điểm benchmark.

Code tiếng Việt được giữ cho nhánh thực nghiệm riêng sau này; MIMIC Mini không còn là database mục tiêu. Benchmark runner không dịch câu hỏi hoặc diễn giải kết quả sang tiếng Việt. Nhánh tiếng Việt sẽ được đánh giá riêng sau.

## Phương pháp so sánh

Hệ thống đề xuất là pipeline full agentic hiện tại được chuyển sang BigQuery/English. Ba baseline dự kiến: CLINSQL CoT + Self-Refinement, MAC-SQL với Selector/Decomposer/Refiner, và SDE-SQL zero-shot với SQL probes. Bốn workflow đã có đường chạy mock; MAC-SQL/SDE-SQL còn thiếu parity với source gốc nên chưa dùng để báo điểm. Không fine-tuning. Mọi hệ thống phải dùng chung dữ liệu, model, dialect, nguồn tri thức hợp lệ, evaluator và chính sách chống leakage; số agent, retrieval và số API calls được đo như đặc trưng phương pháp.

Xem [trạng thái triển khai theo từng yêu cầu](IMPLEMENTATION_STATUS.md), [protocol](EXPERIMENT_PROTOCOL.md), [nhật ký thích nghi baseline](BASELINE_ADAPTATION.md), [kiến trúc](FULL_AGENTIC_ARCHITECTURE.md) và [hướng dẫn ứng dụng](HUONG_DAN_CHAY.md).

Source chính thức của cả ba paper đã được khóa trong `external/`; xem [kiểm kê ba hệ thống](PAPER_SYSTEMS.md), [đối chiếu thuật toán](PAPER_ALGORITHM_AUDIT.md) và chạy `python paper_sources.py` để xác minh. Source gốc chưa được port/chạy trên cùng BigQuery và GPT-5-mini.

## Lệnh hiện có

```powershell
python run.py test -q --basetemp .pytest_run
python run.py clinsql-inspect --official-root external/clinsql_official
python run.py bigquery-preflight
```

`clinsql-inspect` chỉ đọc câu hỏi và chia validation; `bigquery-preflight` mặc định chỉ in plan 22 HOSP/9 ICU. Cả hai không gọi BigQuery hay API. Chỉ chạy pilot validation sau khi kiểm tra quyền dữ liệu, kết nối, scorer và chi phí. Test chính thức chỉ chạy khi cấu hình đã khóa.

Sau khi cấu hình ADC, dùng `bigquery-preflight --discover-location` để đọc location của hai dataset (không tạo query job), rồi đặt `BQ_LOCATION`. Preflight metadata thật chỉ chạy bằng `--execute-metadata` sau khi cấu hình các biến `BQ_*`. Xem [báo cáo metadata integration](BIGQUERY_METADATA_INTEGRATION_REPORT.md).
