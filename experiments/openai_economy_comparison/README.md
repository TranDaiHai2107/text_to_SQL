> Kết quả cuối đã hoàn tất trong `../openai_economy_standard_finish/runs/gpt6luna_none_complete_20261030_once/RESULTS_VI.md`: Luna/none, một pass; các lượt trước được giữ làm lịch sử.

# Một lượt V5 + Vanna với OpenAI tiết kiệm

Theo yêu cầu thay đổi ngày30/10/2026: chạy đủ hai hệ thống đúng một lượt, không tối ưu theo điểm rồi chạy nhiều vòng. Giữ nguyên hệ thống Vanna và tất cả output cũ. Lượt Terra/high đã dừng với193câu paired; không tự tiếp tục, không trộn SQL Terra vào lượt này.

Model **gpt-6-luna**, `reasoning.effort=none`, `service_tier=flex`, `store=false`, max output4.096token. API preflight đã xác nhận completed/Flex/none và0reasoningtoken. Tài liệu hiện hành ghi GPT-4.1 nano đã shut down; Luna là lựa chọn tiết kiệm hiện hành đã kiểm tra có quyền truy cập và hỗ trợ tắt reasoning. Không tự nâng model hoặc chuyển về Standard/Fast nếu Flex thiếu tài nguyên.

Giá Flex tham chiếu: input$0,05/M, output$0,25/M; cache có biểu giá riêng. Guard dùng giá cache-write cao hơn cho mọi input ($0,0625/M) + output$0,25/M để ước lượng bảo thủ, dừng trước khi tổng ước lượng và phần dự trữ vượt$3 cho lượt mới. Đây không phải billing cap của nhà cung cấp hoặc invoice; không bao gồm chi phí Terra đã phát sinh trước khi đổi yêu cầu.

V5 giữ nguyên retrieval/prompts, compiler metadata và policy strict3_canonical. V5 vẫn có ba nhánh generation + tối đa một sửa lỗi execution mỗi nhánh; Vanna native có một nhánh. “Một lượt” nghĩa là mỗi hệ thống đánh giá toàn bộ1.167câu một lần, không phải chỉ một API call cho cả benchmark. Vanna+GEF dùng chung SQL, không gọi thêm model. Cùng model không đồng nghĩa cùng inference budget; báo rõ giới hạn này.

Train+dev6.287câu làm knowledge, test1.167câu gốc để chấm. Không fit threshold trên test, không chạy thêm database/chuyển ngữ/ASR/SQL→text. Scorer là official core trên host; không gán nhãn Docker verified khi chưa đối chiếu. Đây vẫn là test đã dùng, không phải independent holdout.

```powershell
.venv/Scripts/python.exe -m unittest discover -s experiments/openai_economy_comparison/tests -v
.venv/Scripts/python.exe experiments/openai_economy_comparison/run.py --workers 16
```

Chỉ chạy một run mặc định `gpt6luna_none_flex_20261030_once`. Resume dùng checkpoint và cache đúng hash; không gọi lại các request đã xong. Khi hoàn tất, chạy lại cùng lệnh chỉ trả kết quả đã lưu, không inference thêm. API/quota/budget/response incomplete làm dừng có checkpoint, không pad câu thiếu thành null. Không chấm final trước khi đủ1.167câu cả hai hệ thống. Không lưu API key/raw reasoning trong output; key nằm ở root `.env` đã ignore.

Kết quả: `runs/gpt6luna_none_flex_20261030_once/RESULTS_VI.md`, `evaluation.json`. Tiến độ: `STATUS.json`.

[Model](https://developers.openai.com/api/docs/models/gpt-6-luna) · [Flex](https://developers.openai.com/api/docs/guides/flex-processing) · [Trạng thái model cũ](https://developers.openai.com/api/docs/models/gpt-4.1-nano)
