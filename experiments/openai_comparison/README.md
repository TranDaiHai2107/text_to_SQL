> Kết quả cuối đã hoàn tất trong `../openai_economy_standard_finish/runs/gpt6luna_none_complete_20261030_once/RESULTS_VI.md`: Luna/none, một pass; các lượt trước được giữ làm lịch sử.

# V5 + Vanna với OpenAI reasoning

Model do người dùng chọn: **gpt-6.1-terra**, reasoning **high** cho cả V5 và Vanna. Dùng Responses API, `store=false`, service tier `default`; max output 32.768 token bao gồm reasoning và câu trả lời cuối. Không truyền tham số DeepSeek thinking, temperature hoặc logprobs sang OpenAI.

Key chỉ đọc từ `.env` được Git ignore. Không lưu key trong config/checkpoint/log. Không sửa V5/DeepSeek hoặc score cũ. Không fine-tune. Lượt chạy mới giữ generation/retrieval của V3, compiler V5 và policy `strict3_canonical` đã chốt; chỉ đổi transport/model và bật reasoning high cho tất cả route như yêu cầu. Không chọn lại threshold trên test.

V5 có ba route (và tối đa một sửa lỗi schema/execution mỗi route); Vanna dùng native legacy SQL/RAG của Vanna2.0.2, một lượt có reasoning high. Thêm Vanna+GEF từ cùng SQL, không gọi model thêm. Cùng backbone/reasoning không có nghĩa cùng chi phí. Train+dev 6.287 ví dụ làm knowledge; chỉ chấm đủ 1.167 test gốc bằng official scorer. Đây vẫn là đánh giá exploratory trên test đã dùng, không phải xác nhận độc lập. Không triển khai thêm database, ASR, chuyển ngữ hay SQL→text ở bước này.

```powershell
.venv/Scripts/python.exe -m unittest discover -s experiments/openai_comparison/tests -v
.venv/Scripts/python.exe experiments/openai_comparison/run.py --run-name gpt61terra_high_20261030_r1 --workers 16
```

Có thể dùng `--limit 8 --workers 4` cho kiểm tra vận hành rồi chạy lại cùng run name không limit; sẽ dùng checkpoint/cache đúng hash và không chấm final khi thiếu câu. Không có test-gold trong generation. API quota/auth/model errors/incomplete output dừng và giữ checkpoint; không padding bằng null. Cache Responses chứa final SQL/usage, không raw reasoning. Token output đã bao gồm reasoning, không cộng thêm lần nữa. Không thay model tự động nếu key thiếu quyền.

Kết quả nằm trong `runs/<run-name>/evaluation.json`, `RESULTS_VI.md`; `STATUS.json` ghi tiến độ. Không gán nhãn Docker verified cho vòng chỉ chấm host official core. Giữ paper RS10 74,21 làm mốc lịch sử, chưa chạy lại model tác giả.

[Model chính thức](https://developers.openai.com/api/docs/models/gpt-6.1-terra) · [Reasoning API](https://developers.openai.com/api/docs/guides/reasoning)
