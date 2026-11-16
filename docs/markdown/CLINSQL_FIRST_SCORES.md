# Điểm rubric CLINSQL đầu tiên — 16/11/2026

**Judge `ADAPTED_JUDGE_GPT5MINI_2025_08_07`.** Snapshot `gpt-5-mini-2025-08-07` qua `https://api.openai.com/v1/chat/completions`, `store=false`, không đặt `temperature` hoặc `max_completion_tokens` trong cấu hình tính điểm. Config SHA-256 `129e16b69429c90b77b9253904a492b84737da0f4d3d7b8e535452f6c4f2fbc3`.

## Kết quả năm câu development đã khóa

Mỗi dòng ghi SQL Score của hai dự đoán cùng câu hỏi. **Execution Score của cả 10 dự đoán là `UNSCORED_DATA_EGRESS`**, để trống giá trị số. Không có trung bình Execution Score.

- **Diagnostic Procedures · Easy/058** — CoT **0,181818**, SDE-SQL **0,181818**.
- **Vital Signs Monitoring · Easy/044** — CoT **0,300000**, SDE-SQL **0,000000**.
- **Laboratory Results Analysis · Medium/079** — CoT **0,300000**, SDE-SQL **0,300000**.
- **Medication Management · Medium/012** — CoT **0,250000**, SDE-SQL **0,250000**.
- **Patient Demographics and Admissions · Hard/058** — CoT **0,433333**, SDE-SQL **0,333333**.

**Trung bình SQL Score** — CoT **0,293030** trên 5/5 case, SDE-SQL **0,213030** trên 5/5 case. Đây là điểm pilot với judge thay thế.

## Cách chấm và usage

- Kiểm tra SHA-256 của 10 checkpoint cùng result artifacts đã lưu. Chấm đủ **116/116 lá SQL** bằng cây rubric, hàm dựng prompt, thứ tự duyệt và phép tổng hợp critical-first, sequential, weighted của source ghim. Input judge chỉ gồm câu hỏi, predicted SQL và rubric SQL. Giữ nguyên cây rubric kết quả và để **104 lá kết quả** chưa chấm vì điều kiện truyền result rows chưa được xác minh. Không gọi lại inference của CoT/SDE và không gọi BigQuery.
- Trần 1.024 token của lượt thử làm một phản hồi bị cắt. Điểm báo cáo dùng cấu hình bỏ trần, giữ nguyên cây và prompt. Adapter đọc điểm nhị phân tường minh khi judge trả chữ thường, Markdown hoặc JSON. Một phản hồi JSON hai dòng đã được đọc lại từ ledger mà không gọi lại API cho lá đó. Các lượt sai định dạng được hạch toán đầy đủ và có giới hạn retry.
- **147 Chat Completions có receipt**, gồm 142 lượt rubric và 5 lượt preflight tổng hợp. Có 5 lượt tra snapshot metadata và 1 reservation của lượt thử ban đầu chưa có receipt. Tổng usage đối soát **139.152 input tokens**, **115.918 output tokens**, ước tính **0,26420480 USD**, chưa tính reservation chưa xác nhận. [OpenAI GPT-5 mini pricing](https://developers.openai.com/api/docs/models/gpt-5-mini)
- [Điểm và thông số judge trong restricted storage](<D:/Github/text_to_SQL/results/restricted/rubric_sql_recovery_b839d0f631812ab4/scores.json>). Hạn lưu của lượt chấm lấy theo artifact hết hạn sớm nhất, **21/11/2026 01:52 UTC+7**.
