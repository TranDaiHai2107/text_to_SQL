# Áp dụng hệ thống của mình lên EHRSQL

**Trạng thái 23/10/2026:** người dùng quyết định chờ cấu hình GPT trước khi chạy benchmark đầy đủ. Các lời gọi Groq đã dừng. Chưa có điểm test cuối cùng của hệ thống. Xem `STATUS.json`.

## Đã chuẩn bị

- Database/câu hỏi dùng đúng snapshot ProbGate/EHRSQL trong `../../baselines/probgate_ehrsql_2024`, không thay database của ứng dụng chính.
- Ba tầng Chroma riêng: từ điển y khoa 6.417 mục, schema 17 bảng và 5.124 ví dụ train. Không đưa gold dev/test vào prompt/index; không gửi hàng kết quả bệnh nhân tới model.
- Pipeline tiếng Anh/SQLite: model thuần; ba RAG; schema validation + tự sửa tối đa hai lần; rewrite đa lượt gốc (identity vì EHRSQL không có history); nhánh mở rộng standalone rewrite có guard; GEF lấy từ hướng ProbGate để lọc SQL lỗi/kết quả rỗng.
- Groq không cung cấp token logprobs tương ứng nên không giả lập ProbGate bằng confidence tự đặt.
- Bộ chấm official RS0/RS5/RS10/RSN, EX trên câu answerable, VSR; so sánh paired cùng ID với model thuần và cache tác giả. Tập chạy dở không được padding null hoặc đem so với điểm toàn bộ paper.
- `finalize_full.py` chỉ chấp nhận đủ 1.167 ID test rồi chấm lại bằng Docker baseline cùng protocol/runtime.
- Cache từng lời gọi, checkpoint từng stage, cấu hình/hash code cố định để chạy tiếp và phân biệt các thí nghiệm.
- Sáu kiểm thử pipeline đã đạt trước khi thử API.

## Những gì đã thực chạy

- `runs/dev_high_v1`: thử reasoning high/4.096 token trên dev; các response dùng hết token cho reasoning và không trả SQL. Sau đó API chặn output request ở OTPM1.000. Đây là kiểm tra cấu hình không phù hợp, không phải điểm benchmark.
- `runs/dev_max_probe`: thử ngân sách 16.384 token, API vẫn báo giới hạn tài khoản; không có kết quả test.
- `runs/dev_quota_v1`: chạy được một câu dev đầy đủ các nhánh ở chế độ không reasoning, trước khi người dùng yêu cầu chờ GPT. Không dùng một câu dev này để kết luận cải thiện.

## Khi có GPT

`model_client.py` hiện vẫn là client **Groq**, chưa có OpenAI/GPT API adapter. Cần cấu hình provider/model và client GPT trước, không chỉ đổi model ID vào Groq. Giữ cùng một model GPT và cùng cấu hình generation cho nhánh thuần/nhánh đề xuất để đánh giá đóng góp phương pháp. Không gọi model GPT mới là model GPT fine-tuned riêng của tác giả.

Chọn ngân sách token phù hợp với model/quota mới; kiểm tra trên dev rồi đóng băng cấu hình trước test. Dùng run name mới để không trộn kết quả Groq và GPT. Chỉ index train, không chỉnh prompt/threshold dựa trên gold test. Primary metric đã dự kiến là RS10; nhánh đầy đủ là `three_rag_standalone_rewrite_agentic_gef`.

## Các file chính

- `settings.py`: đường dẫn và model hiện tại.
- `retrieval.py`: index/retrieval ba tầng trên schema EHRSQL.
- `pipeline.py`: các cấu hình, rewrite, generation, self-correction và GEF.
- `sql_runtime.py`: SQLite chỉ đọc và schema validation.
- `model_client.py`: Groq, accounting, cache và xử lý rate limit.
- `run.py`: inference/resume, không đọc gold test.
- `evaluate.py`: chấm các câu paired hoàn tất, tách khỏi inference.
- `finalize_full.py`: chấm full test lại trong Docker baseline.
- `run_groq.ps1`: helper Groq cho hai profile `current_quota`/`maximum`; hiện chưa chạy tiếp theo quyết định của người dùng.

Không có lịch tự động chạy tiếp. Chỉ tiếp tục inference khi người dùng cấu hình model và yêu cầu chạy.
