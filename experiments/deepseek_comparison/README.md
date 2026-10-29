# DeepSeek Flash: hệ thống đề xuất, Vanna và paper

Yêu cầu ngày 28/10/2026: chạy `deepseek-flash` cho cả hệ thống đề xuất và Vanna; train + dev làm knowledge base, chỉ test để chấm. Không fine-tune. Không thay key vào app Groq để giả lập provider mới.

## Protocol cố định trước khi chạy

- Knowledge: train 5.124 + dev 1.163 = **6.287 câu**. Corpus/index mới, tách khỏi index train-only cũ.
- Test: đủ **1.167 ID**, 934 answerable và 233 unanswerable. Không đưa SQL/đáp án test vào index/prompt.
- Cả hai dùng DeepSeek Flash, thinking **disabled**, temperature yêu cầu 0, output tối đa 2.048 token. Không gửi seed vì API không công bố tham số này. Ghi model/fingerprint/usage theo từng response.
- Hệ thống đề xuất: `full_schema_rag`, `full_schema_rag_agentic`, `full_schema_rag_agentic_gef`. Ba nhánh dùng chung SQL ban đầu; chỉ sửa nếu SQL lỗi, tối đa hai lần. Primary đã chọn trước: `full_schema_rag_agentic_gef`.
- Vanna: pipeline SQL/RAG legacy trong package 2.0.2; `vanna` và hậu xử lý bổ sung `vanna_gef`. Dùng chung SQL, không sửa tự động. Primary `vanna`; báo thêm `vanna_gef` làm đối chứng cùng bộ lọc.
- Không bật rewrite cho benchmark câu hỏi độc lập ở lượt chính. Không chạy lại toàn bộ các ablation phát sinh thêm generation để ưu tiên hoàn thành hai hệ thống với số dư hiện có.
- Logprobs được API xác nhận hỗ trợ và sẽ lưu, nhưng **không chọn ngưỡng từ gold test**. Chưa áp ProbGate confidence gate vào output mới.
- Không gửi hàng kết quả bệnh nhân hoặc reasoning content cho API/lưu vào log. Chỉ gửi câu hỏi, DDL, tài liệu và ví dụ knowledge được cho phép.

## Ý nghĩa phép so sánh

Hệ thống đề xuất và Vanna dùng cùng backbone, cùng corpus và generation settings; vẫn cần báo số lượt gọi/token vì nhánh sửa lỗi có thể dùng thêm tài nguyên. Schema/examples retrieval và prompt khác nhau theo phương pháp, được lưu trong source/config.

Paper dùng model fine-tuned và quy trình dữ liệu khác. **Dùng thêm dev làm knowledge là khác biệt điều kiện thí nghiệm**; điểm cao hơn paper chỉ là kết quả so sánh ở mức hệ thống trong điều kiện đã nêu, không tự chứng minh phương pháp vượt tác giả dưới cùng điều kiện.

RS0/RS5/RS10/RSN theo EHRSQL official. EX/VSR tính bổ sung bằng evaluator chung, không gán là số paper đã công bố. Baseline tham chiếu là official replay SQL/logprobs cache tác giả, không phải đã gọi model fine-tuned của họ.

## Chạy/resume

Key lấy từ `.env`, không đưa vào source, command line hoặc report. `.env` được Git ignore. Hai index train+dev được chuẩn bị cục bộ trước khi inference; không gọi LLM khi tạo index.

Từ thư mục gốc:

```powershell
.\.venv\Scripts\python.exe -X utf8 -B experiments/deepseek_comparison/run_deepseek.py --run-name deepseek_flash_train_dev_20261028_v1 --workers 8
```

Runner dùng hai ledger/cache riêng, kiểm soát concurrency và atomic paired checkpoints. Cùng một cohort ID đã hoàn tất cho cả hai hệ thống. Dừng khi thiếu số dư hoặc lỗi API, không đổi model hoặc padding ID thiếu thành null. Sau khi model calls kết thúc mới nạp gold để chấm và phân tích lỗi.

Run mới nằm trong `runs/` của mỗi hệ thống và `experiments/deepseek_comparison/runs/`. Mỗi nơi có config hash đóng băng. Không sửa source/config rồi resume cùng tên. Các kết quả Qwen/Groq trước đó không được trộn vào.

## Kết quả

`STATUS.json` ghi tiến độ paired. Sau khi kết thúc: `runs/<run>/comparison.json`, `RESULTS.md` và `error_analysis.json` (khi full test) ghi điểm, token, chênh lệch paired và giới hạn diễn giải. Báo cáo partial không được so với full paper. Đề xuất cải thiện sau phân tích là kế hoạch cho nghiên cứu tiếp theo, không tự chỉnh phương pháp bằng test rồi chọn điểm đẹp hơn.

Số dư khi kiểm tra ban đầu: 2 USD. Không tự mua thêm credit; hết số dư sẽ lưu checkpoint để tiếp tục khi tài khoản được nạp.

Nguồn API: [DeepSeek Chat Completions](https://api-docs.deepseek.com/api/create-chat-completion/), [thinking mode](https://api-docs.deepseek.com/guides/thinking_mode/), [balance](https://api-docs.deepseek.com/api/get-user-balance/).
