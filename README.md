# Hệ thống MIMIC-IV và hướng nghiên cứu CLINSQL

## Định hướng triển khai

- **Đích chung:** MIMIC-IV v3.1 trên BigQuery cho hệ thống đề xuất và đánh giá CLINSQL 2026.
- **Trạng thái code:** ứng dụng Streamlit hiện vẫn kết nối PostgreSQL/MIMIC Mini; đây là đường chạy cũ. Nền BigQuery/English tại `src/ehrqa/clinsql/` mới ở mức offline, chưa có kết nối, lượt chạy model hoặc điểm benchmark.

Code tiếng Việt được giữ cho nhánh thực nghiệm riêng sau này; MIMIC Mini không còn là database mục tiêu. Benchmark runner không dịch câu hỏi hoặc diễn giải kết quả sang tiếng Việt. Nhánh tiếng Việt sẽ được đánh giá riêng sau.

## Phương pháp so sánh

Hệ thống đề xuất là pipeline full agentic hiện tại được chuyển sang BigQuery/English. Ba baseline dự kiến: CLINSQL CoT + Self-Refinement, MAC-SQL với Selector/Decomposer/Refiner, và SDE-SQL zero-shot với SQL probes. Chỉ CLINSQL CoT có khung offline; MAC-SQL và SDE-SQL chưa tích hợp. Không fine-tuning. Mọi hệ thống phải dùng chung dữ liệu, model, dialect, nguồn tri thức hợp lệ, evaluator và chính sách chống leakage; số agent, retrieval và số API calls được đo như đặc trưng phương pháp.

Xem [protocol](EXPERIMENT_PROTOCOL.md), [nhật ký thích nghi baseline](BASELINE_ADAPTATION.md), [kiến trúc](docs/system/FULL_AGENTIC_ARCHITECTURE.md) và [hướng dẫn ứng dụng](docs/guides/HUONG_DAN_CHAY.md).

## Lệnh hiện có

```powershell
python run.py test -q --basetemp .pytest_run
python run.py clinsql-inspect --questions <validation.json>
python run.py app
```

`clinsql-inspect` chỉ đọc câu hỏi và chia validation; không gọi BigQuery hay API. Chỉ chạy pilot validation sau khi kiểm tra quyền dữ liệu, kết nối, scorer và chi phí. Test chính thức chỉ chạy khi cấu hình đã khóa.
