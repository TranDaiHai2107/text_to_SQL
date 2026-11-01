# V6 — thử cải tiến trên đúng dataset paper, rồi đánh giá SQL và câu trả lời tiếng Anh

Lượt ngày 01/11/2026 tách khỏi V5 đã chốt. Không đổi database, gold, official scorer, ứng dụng tiếng Việt hoặc các kết quả Vanna/tác giả. Chỉ dùng EHRSQL 2024 của paper: train 5.124, dev 1.163, test 1.167.

## Phạm vi chạy lại

V6 kế thừa **đúng các ứng viên DeepSeek Flash đã sinh cho V5**, chạy lại các bước sửa/kiểm tra SQL, chọn prediction, thực thi SQLite và chấm. Không gọi model để sinh lại ứng viên; incremental API call = 0. Chi phí model của generation nguồn vẫn tồn tại và không được ghi thành 0 cho toàn hệ thống. Cách này giữ generation cố định để quan sát tác động riêng của gói hậu xử lý.

Không có retrieval mới, fine-tune, GraphRAG hay LLM verifier trong lượt này. Nghiên cứu các công nghệ đó được ghi ở [RESEARCH.md](RESEARCH.md), phân biệt nguồn tham khảo với code thực sự áp dụng.

## Đã thêm và thử

- Chuẩn hóa AST bằng SQLGlot cho cột kỳ dư trong truy vấn aggregate theo daily/weekly/monthly/yearly, theo quy ước output EHRSQL có bằng chứng train. Không bỏ cột kỳ được yêu cầu rõ; không sửa khi có ORDER BY ordinal có thể đổi nghĩa truy vấn.
- Bổ sung điều kiện `org_name IS NOT NULL` cho trường hợp positive first/last organism phù hợp với quy ước gold train (84/84 ví dụ). Đây là heuristic của benchmark, không phải suy luận lâm sàng phổ quát; không áp dụng câu hỏi phủ định/missing/unknown/NULL.
- Chuẩn hóa hoa/thường của literal mã ICD khi đúng dictionary có **một** giá trị vật lý phù hợp. Không đoán mã, không dùng gold của câu đang đánh giá.
- Các proposal được thực thi read-only; proposal lỗi/rỗng giữ lại V5. Không sửa genuine model-null hoặc output bị cắt. Có evidence và snapshot nguồn.
- Thử grid 8 policy gồm V5, V6 strict-three và các fallback hai phiếu có điều kiện. **Chọn bằng RS10 của tune 300, không bằng test.**

100 câu audit lịch sử cũng đã được xem để phát triển rule, vì vậy được khai báo là **development đã tiếp xúc**, không phải kiểm định độc lập. Toàn bộ test cũ cũng có exposure lịch sử từ quá trình phát triển V5; lượt này chỉ cam kết không dùng kết quả test mới để chọn/retune V6.

## Review và khóa trước test

[REVIEW.md](REVIEW.md) ghi hai lỗi được phát hiện và sửa trước test: bỏ projection làm đổi `ORDER BY 1 LIMIT 1`, và bỏ cột kỳ dù câu hỏi yêu cầu `by/per/for each month`. Có regression test SQLite thực tế. Lượt `runs/dev_selected_20261101_once` là diagnostic trước review, được đánh dấu obsolete, không dùng cho test.

Lượt chính: `runs/reviewed_20261101_once`. `protocol.json`, `policy.json`, `TEST_LOCK.json` khóa code, policy, nguồn candidates và manifest nhãn tiếng Anh. Chỉ primary được chọn từ dev và V5 đối chứng được chấm trên test. `TEST_COMPLETE.json` ngăn chạy lại test để tìm điểm tốt hơn.

## English → SQL → English

`english_evaluation.py` dùng **SQL prediction thực tế**, chạy database rồi tạo câu trả lời bằng renderer tiếng Anh theo mẫu đã audit. Nó lưu `english_predictions.jsonl` trước khi đọc English reference để chấm. SQL lỗi không đổi thành từ chối đúng. So sánh V5 và V6 dùng cùng renderer và bộ dữ liệu mở rộng.

Chỉ số gồm raw/normalized EM, token F1, ROUGE-L, WER, controlled fact-EM và parse coverage; báo riêng nhóm answerable/unanswerable. Fact-EM kiểm tra toàn bộ numeric3 rows, không cap100 như official SQL scorer. Không gán các điểm tiếng Anh mới cho paper.

`oracle_renderer` dùng gold SQL để kiểm tra riêng renderer, ghi rõ **functional oracle, không phải kết quả mô hình**. Cả oracle và end-to-end đều dùng nhãn English tự sinh theo mẫu, chưa phải gold hội thoại được chuyên gia thẩm định.

## Chạy

Từ project root, sau khi quyết định run mới và giữ code ổn định:

```powershell
python experiments/ours_improved_v6/run_v6.py --phase dev
python experiments/ours_improved_v6/run_v6.py --phase test
python experiments/ours_improved_v6/evaluate_english_runs.py
```

Hai lệnh sau chỉ chạy sau khi dev tạo TEST_LOCK. Không đổi code hay policy sau khi khóa. Các lệnh này không gọi API. Script English giữ lại output đã hoàn tất, không ghi đè prediction cũ.

## Kết quả và bằng chứng

- [Báo cáo cuối tiếng Việt](runs/reviewed_20261101_once/FINAL_REPORT_VI.md).
- [Số liệu cuối JSON](runs/reviewed_20261101_once/FINAL_RESULTS.json).
- `TEST_RESULTS.xml`: 109 test và 5 subtest trước test thật.
- [Evidence trên dev](DEV_FINDINGS.md), [nghiên cứu nguồn chính thống](sources.json).
- `FINAL_AUDIT.json` / `FINAL_AUDIT.md`: đối soát độc lập kết quả sau chạy.

V5 vẫn giữ nguyên làm mốc đã chốt; V6 là thí nghiệm cải tiến. Chênh lệch quan sát trên tập cũ không tự chứng minh ưu thế phương pháp hoặc khả năng tổng quát hóa độc lập.
