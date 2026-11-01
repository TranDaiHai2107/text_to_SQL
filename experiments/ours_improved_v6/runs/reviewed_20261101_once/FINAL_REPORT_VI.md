# V6 — kết quả phát triển và chạy lại trên dataset paper

Ngày 01/11/2026. Chỉ EHRSQL 2024/MIMIC-IV snapshot của paper; không chuyển ngữ hoặc dataset khác.

## Phương pháp và lựa chọn

Tái sử dụng các ứng viên DeepSeek Flash đã sinh cho V5, bổ sung chuẩn hóa AST/output contract, literal ICD theo metadata và quy ước organism có bằng chứng train. Giữ nguyên model, generation, database, gold và official scorer. Incremental API call = 0; chi phí generation kế thừa không bằng 0.

Research đối chiếu CHESS/DAIL-SQL về grounding/retrieval, PromptMind về đồng thuận thực thi, CHASE-SQL về candidate selection và nghiên cứu selective prediction. Đây là adaptation có giới hạn; không tái hiện nguyên các phương pháp đó, không fine-tune, không thêm GraphRAG hoặc verifier LLM chưa được đánh giá.

Grid 8 policy khai báo trước; chọn trên 300 tune: **v6_strict3**. 100 câu development còn lại đã tiếp xúc khi phân tích rule, chỉ dùng mô tả; không gọi là audit độc lập. Khóa policy và hash code trước test. Chỉ chấm primary đã khóa và V5 đối chứng, không chọn lại sau khi xem test.

Hai lỗi projection phát hiện trong code review (ORDER BY ordinal và yêu cầu cột kỳ rõ ràng) đã sửa trước test. Lượt dev trước review được đánh dấu obsolete, không dùng làm kết quả test.

## Text-to-SQL — đủ 1.167 câu

- **V5_frozen**: RS0=92.89; RS5=83.89; RS10=74.89; RSN=-2007.11; EX=92.29%; VSR=75.66%; precision=97.62%. SQL đúng=862; từ chối đúng=222; sai=21; từ chối nhầm=62.
- **V6_dev_selected**: RS0=92.97; RS5=83.98; RS10=74.98; RSN=-2007.03; EX=92.40%; VSR=75.75%; precision=97.62%. SQL đúng=863; từ chối đúng=222; sai=21; từ chối nhầm=61.

Chênh RS10 V6−V5: **+0.0857 điểm**. Bootstrap ghép theo câu hỏi 95% [0.00; 0.26], chỉ mang tính exploratory, không xác nhận trên holdout mới.

Chuyển trạng thái từng câu: {"correct -> correct": 1084, "abstained_answerable -> abstained_answerable": 61, "wrong -> wrong": 21, "abstained_answerable -> correct": 1}.

Có 1 câu có proposal ứng viên được chấp nhận; 1 SQL cuối khác V5. Số phép sửa theo loại: {"unique_casefold_physical_ICD_code": 2}.

Đối chứng đã audit trước đó: Vanna DeepSeek RS10 −58,10; Vanna+GEF −12,08; ProbGate 74,21. RS là số paper; EX/VSR của paper trong báo cáo chung được tính bổ sung từ released predictions. Không chạy lại Vanna hoặc model fine-tuned tác giả ở lượt này.

## English → predicted SQL → controlled English

Câu trả lời được tạo từ SQL prediction thực tế và database read-only, lưu file trước khi đọc reference tiếng Anh. Generator là renderer theo mẫu, không phải LLM sinh ngôn ngữ tự do. Dùng cùng renderer cho V5 và V6; không dùng gold result để sửa prediction.

- **V5_frozen**: n=1167; controlled fact-EM=92.89%; parse coverage=100.00%; raw EM=92.89%; normalized EM=92.89%; token F1 macro=94.12%; ROUGE-L F1 macro=94.11%; WER=14.32%.
  Fact-EM riêng 934 câu có đáp án=92.29%; 233 câu không thể trả lời=95.28%.
- **V6_dev_selected**: n=1167; controlled fact-EM=92.97%; parse coverage=100.00%; raw EM=92.97%; normalized EM=92.97%; token F1 macro=94.20%; ROUGE-L F1 macro=94.18%; WER=14.29%.
  Fact-EM riêng 934 câu có đáp án=92.40%; 233 câu không thể trả lời=95.28%.
- **oracle_renderer**: n=1167; controlled fact-EM=100.00%; parse coverage=100.00%; raw EM=100.00%; normalized EM=100.00%; token F1 macro=100.00%; ROUGE-L F1 macro=100.00%; WER=0.00%.

**oracle_renderer dùng gold SQL** để kiểm tra riêng chức năng SQL→text. Không được dùng điểm oracle làm điểm hệ thống hoặc chứng minh model hoàn hảo.

Nhãn tiếng Anh là bộ mở rộng tự xây đã audit, chưa phải official English-answer benchmark hoặc bác sĩ thẩm định. Fact-EM yêu cầu grammar chuẩn và full numeric3 rows, không cap100; khác với official SQL scorer. WER/F1/ROUGE chỉ đo giống từ ngữ. Không gán các điểm tiếng Anh này cho paper.

## Kết luận

V6 cải thiện điểm quan sát so với V5 trên cùng generation và dataset. Có bằng chứng ích lợi của gói chuẩn hóa/selection trong phép thử này; chưa chứng minh khả năng tổng quát hóa hay ưu thế nghiên cứu độc lập. V5 bản chốt được giữ nguyên để đối chiếu.

Chi tiết đầy đủ, mẫu số, nhóm câu hỏi, hash và nguồn: FINAL_RESULTS.json. Nghiên cứu và review trước test nằm ở ../../RESEARCH.md và ../../REVIEW.md.
