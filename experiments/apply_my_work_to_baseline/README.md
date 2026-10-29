# Áp dụng hệ thống của mình lên EHRSQL

**Kết quả mới ngày 28/10/2026:** đã chạy đủ 1.167 câu test bằng DeepSeek Flash, knowledge train+dev gồm 6.287 câu, không fine-tune. Primary đạt EX 88,12%, RS10 −49,10; chưa vượt ProbGate theo RS10. Điểm đã chấm lại trong Docker. Xem [báo cáo cuối](../deepseek_comparison/runs/deepseek_flash_train_dev_20261028_v1/FINAL_REPORT.md) và [phân tích/cải thiện](../deepseek_comparison/runs/deepseek_flash_train_dev_20261028_v1/RECOMMENDATIONS.md). Các trạng thái Groq/GPT bên dưới là lịch sử chuẩn bị trước lượt này.

**Trạng thái 24/10/2026:** đã cải thiện pipeline và kiểm thử cục bộ; inference vẫn dừng theo yêu cầu trước đó. Chưa có điểm test cuối cùng của hệ thống. Client hiện chỉ có Groq; cần adapter tương ứng nếu chọn GPT/Gemini/DeepSeek. Xem `STATUS.json` và [các thay đổi trước khi chạy](PRE_RUN_IMPROVEMENTS.md).

## Đã chuẩn bị

- Database/câu hỏi dùng đúng snapshot ProbGate/EHRSQL trong `../../baselines/probgate_ehrsql_2024`, không thay database của ứng dụng chính.
- Ba tầng Chroma riêng: từ điển y khoa 6.417 mục, schema 17 bảng và 5.124 ví dụ train. Không đưa gold dev/test vào prompt/index; không gửi hàng kết quả bệnh nhân tới model.
- Pipeline tiếng Anh/SQLite: model thuần; ba RAG; schema validation + tự sửa tối đa hai lần; rewrite đa lượt gốc (identity vì EHRSQL không có history); nhánh mở rộng standalone rewrite có guard; GEF lấy từ hướng ProbGate để lọc SQL lỗi/kết quả rỗng.
- Client hiện chưa thu nhận token logprobs cần cho ProbGate. Chưa có nhánh ProbGate hoàn chỉnh trên model mới; không giả lập nó bằng confidence tự đặt. `base_gef` chỉ là đối chứng dùng GEF, không phải toàn bộ ProbGate.
- Bộ chấm official RS0/RS5/RS10/RSN, EX trên câu answerable, VSR; so sánh paired cùng ID với model thuần và cache tác giả. Tập chạy dở không được padding null hoặc đem so với điểm toàn bộ paper.
- `finalize_full.py` chỉ chấp nhận đủ 1.167 ID test rồi chấm lại bằng Docker baseline cùng protocol/runtime.
- Cache từng lời gọi, checkpoint từng stage, cấu hình/hash code cố định để chạy tiếp và phân biệt các thí nghiệm.
- Bộ mặc định mới giữ đủ schema 17 bảng, đối soát RAG ví dụ / thêm từ điển / sửa lỗi, có đối chứng GEF dùng chung SQL. Rewrite và schema pruning vẫn có thể chọn để ablation trên dev.
- Mười hai kiểm thử pipeline/evaluator đã đạt sau cải tiến ngày 24/10. Kiểm thử này không đo độ chính xác model.

## Những gì đã thực chạy

- `runs/dev_high_v1`: thử reasoning high/4.096 token trên dev; các response dùng hết token cho reasoning và không trả SQL. Sau đó API chặn output request ở OTPM1.000. Đây là kiểm tra cấu hình không phù hợp, không phải điểm benchmark.
- `runs/dev_max_probe`: thử ngân sách 16.384 token, API vẫn báo giới hạn tài khoản; không có kết quả test.
- `runs/dev_quota_v1`: chạy được một câu dev đầy đủ các nhánh ở chế độ không reasoning, trước khi người dùng yêu cầu chờ GPT. Không dùng một câu dev này để kết luận cải thiện.

## Khi có GPT

`model_client.py` hiện vẫn là client **Groq**, chưa có OpenAI/GPT API adapter. Cần cấu hình provider/model và client GPT trước, không chỉ đổi model ID vào Groq. Giữ cùng một model GPT và cùng cấu hình generation cho nhánh thuần/nhánh đề xuất để đánh giá đóng góp phương pháp. Không gọi model GPT mới là model GPT fine-tuned riêng của tác giả.

Chọn ngân sách token phù hợp với model/quota mới; kiểm tra trên dev rồi đóng băng cấu hình trước test. Dùng run name mới để không trộn các phiên bản code/provider/model. Chỉ index train, không chỉnh prompt/threshold dựa trên gold test. Primary metric là RS10. Ứng viên mặc định trên dev mới là `full_schema_rag_agentic_gef`; đây chưa phải cấu hình đã chứng minh tốt nhất. Nhánh rewrite cũ vẫn tồn tại để so sánh khi chọn tường minh.

Khi chạy test, bắt buộc truyền `--primary-variant` nằm trong `--modes`, được chọn trước trên dev. Helper PowerShell nhận `-PrimaryVariant`. CLI không kiểm chứng được lịch sử quyết định của người chạy, nên vẫn cần lưu báo cáo dev. Các run Groq cũ không thể resume bằng code mới vì hash khác. Không tự chạy lệnh inference chỉ để thử cấu hình.

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
