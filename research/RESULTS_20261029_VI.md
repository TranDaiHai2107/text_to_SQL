# Kết quả cải thiện hệ thống trên EHRSQL — 29/10/2026

V5 đã hoàn tất đủ1.167câu English→SQL. Primary policy chọn trên300tune, khóa trước100audit mới; primary được đối chiếu official Docker scorer, khớp host từng câu. Không fine-tune LLM, không chạy lại modeltácgiả/Vanna và không thay scorer/gold/database.

## Điểm đã đo

- V2 đầy đủ: RS10=0,00; EX=77,94%.
- V3: RS10=71,21; EX=87,69%.
- V4: RS10=73,09; EX=90,04%.
- **V5: RS0=92,89; RS5=83,89; RS10=74,89; RSN=−2.007,11; EX=92,29%; VSR/coverage=75,66%.**
- [ProbGate paper](https://aclanthology.org/2024.clinicalnlp-1.65/): RS0=81,92; RS5=78,06; RS10=74,21; RSN=−818,08. EX77,73% là số tính bổ sung từreleasedcache, không phải EX paper công bố.

V5 trả lời883câu:862SQL đúng và21sai, precision97,62%. Còn222từ chối đúng và62từ chối nhầm. Paper trả lời735câu với9sai. V5 trả lời được nhiều hơn, không đồng thời giảm số câu sai so paper; RSN củaV5 thấp hơn do phạt lỗi nặng hơn.

## Cải thiện đến từ đâu?

V3 bổ sung categoricalmetadata, truy xuất câu hỏi/cấu trúcSQL và ba đường sinh riêng, rồi chọn bằng đồng thuận thực thi. V4 sửa cách so số về độ chính xác3chữ số của benchmark nhưng giữ fullrows, và kiểm tra formatICD. V5 tạo đề xuất canonicalSQL chỉ khi metadata chứng minh namespace hoặc surfacebinding duy nhất; giữ nguyên outputmodel và log từngliteral được đổi.

SoV3, V5 phục hồi43câu từ chối nhầm thành đúng,0câu xấu đi. RS10 tăng3,68điểm; pairedbootstrap95%[2,66;4,80] trên dữ liệu đã đo. V4→V5 phục hồi21câu nữa. Các so sánh này dùng cùng bộ outputmodel DeepSeekFlash củaV3, không tăng modelgeneration trên test giữaV3/V4/V5. SQL cuốiV5 có thể được compiler sửa literal; không gán đó là outputLLM gốc.

Compiler tạo32candidateproposals trên1.167×3candidates,15trường hợp valid-empty được khôi phục thành nonempty;7SQL cuối được chọn là proposal đã canonicalize. Những proposal khác giúp các voter đồng thuận với một candidate vốn đã đúng.

## Cách kết luận cho khóa luận

Có thể nói: **“Trong thí nghiệm EHRSQL hiện tại, hệ thống đạt RS10=74,89, nhỉnh hơn mốc74,21 củaProbGate; trên cùng outputmodel, gói validation/selection cải thiện so vớiV3.”**

Chưa nên nói: “Đã chứng minh phương pháp vượt trội có ý nghĩa thống kê soProbGate.” ChênhRS10 dùng số chưa làm tròn là+0,6855điểm; pairedbootstrap95%[-9,08;10,20] chứa0. Model/fine-tuning, KBtrain+dev và inference budget cũng khác paper.

Mỗi policy được chọn bằngdev, nhưng đã quan sát điểm test các vòng trước và chốt phiên bản sau khi đạt mục tiêu điểm. Do đó test đã tham gia vòng phát triển. Đây là kết quả exploratory, không phải holdout độc lập. Cần dữ liệu chưa dùng thiết kế/protocol được khóa để xác nhận tổng quát. Scorer giữ nguyên không khắc phục được vấn đề test reuse này.

## Tệp kiểm tra

- [Báo cáoV5](../experiments/ours_improved_v5/runs/deepseek_flash_v5_20261029_r1/FINAL_REPORT.md).
- [Kết quả có source/CI/token](../experiments/ours_improved_v5/runs/deepseek_flash_v5_20261029_r1/FINAL_RESULTS.json).
- [Code và quy trìnhV5](../experiments/ours_improved_v5/README.md).
- [V3 giữ nguyên](../experiments/ours_improved_v3/runs/deepseek_flash_v3_20261029_r2/FINAL_REPORT.md).
- [V4 giữ nguyên](../experiments/ours_improved_v4/runs/deepseek_flash_v4_20261029_r1/FINAL_REPORT.md).

Phạm vi là English→SQL, chưa đánh giá ASR, dịch tiếng Việt hoặc độ trung thành của câu trả lời ngôn ngữ tự nhiên.
