# Kết quả Final Recovery Sprint — 16/11/2026

## Provider controls

- **Route đáp ứng điều kiện truyền dữ liệu MIMIC-IV — NO.** OpenAI Chat Completions và Responses đã trả về đúng `gpt-5-mini-2025-08-07`. Runtime có API key nhưng thiếu định danh organization/project được cấu hình tường minh và thông tin quản trị để tra retention của project. ZDR và việc vô hiệu hóa human-review storage đều `UNVERIFIED`. Hai endpoint gửi `store=false`, tắt lưu request qua tham số API. [OpenAI Data Controls](https://developers.openai.com/api/docs/guides/your-data) · [OpenAI Project Data Retention](https://developers.openai.com/api/reference/resources/admin/subresources/organization/subresources/projects/subresources/data_retention/methods/retrieve)
- **Azure OpenAI.** Runtime thiếu Azure endpoint, credential và deployment. Resource ID, snapshot, request storage và human-review storage đều chưa xác minh được. [Microsoft Azure OpenAI abuse monitoring](https://learn.microsoft.com/azure/foundry/openai/concepts/abuse-monitoring)

## Ours

- **Profile — `PUBLIC_TERMINOLOGY_ADAPTATION` (`PUBLIC_CLINICAL_TERMINOLOGY_SOURCE_ADAPTATION`).** Corpus độc lập gồm 91.199 mã ICD-10-CM FY2022 và ICD-9-CM v32 từ CMS. SHA-256 corpus `f504bb541cf18573e36947b2d59811e9543b278cf398626493e68c6618d4504c`. Thuật toán retrieval, ranking, schema/linker, prompts, Requirement Verification, ba chiến lược sinh SQL và correction dùng cấu hình hiện có. [CMS ICD-10-CM FY2022](https://www.cms.gov/medicare/coding-billing/ICD-10-codes) · [CMS ICD-9-CM v32](https://www.cms.gov/medicare/coding-billing/icd-10-codes/icd-9-cm-diagnosis-procedure-codes-abbreviated-and-full-code-titles)
- **So sánh cục bộ 24 mục Easy/058.** Có 10 mã khớp và nhãn trùng nguyên văn, 0 mã khớp nhưng khác nhãn, 14 mã không có trong corpus đã khóa. Trong 14 mã vắng mặt có 12 ICD-10 procedure ngoài phạm vi ICD-10-CM và 2 mã chẩn đoán ICD-10. Mỗi request linker gửi 24 mục lấy từ corpus CMS độc lập.
- **Easy/058 final SQL — NO. Complete result artifact — NO.** Hai phản hồi Structured Outputs qua kiểm tra schema. Validator sau đó phát hiện một `requirements[].span` không xuất hiện nguyên văn trong câu hỏi ở mỗi phản hồi, lần lượt trên 7 và 8 requirements. Linker kết thúc `StageInterfaceError` sau hai lượt cố định. Case dừng trước SQL generation và BigQuery. Ours có **0/5** SQL cuối và kết quả đầy đủ. Bốn case tiếp theo chưa chạy vì Easy/058 chưa đạt điều kiện chạy tiếp.
- **Ours usage.** 2 Responses API calls đã đối soát, 23.991 input tokens, 6.262 output tokens, gồm 3.072 reasoning tokens. Chi phí ước tính **0,01852175 USD** theo giá token niêm yết. **0 BigQuery jobs, 0 bytes billed**. Checkpoint có SHA-256 khớp state ledger. [Checkpoint](<D:/Github/text_to_SQL/results/restricted/four_method_pilot/ours/public_terminology_recovery/b143a7d68048a0162f073fa64aa5c6e1195f7467682e86ca7468d8bdc3313c75.json>) · [OpenAI GPT-5 mini pricing](https://developers.openai.com/api/docs/models/gpt-5-mini)

## MAC-SQL

- **Easy/058 — `MAC_PRIMARY_EXPERIMENT_EXCLUDED_DATA_EGRESS`.** Selector cần gửi column-value samples từ MIMIC-IV qua Chat Completions. Provider controls của route này chưa được xác minh. Giữ cache 225/225 slots và 378 job lịch sử với 78.744.911.872 bytes billed. Lượt này có **0 GPT-5-mini calls, 0 BigQuery jobs, 0 bytes billed** cho MAC.

## Chấm rubric

CoT và SDE dùng các dự đoán đã lưu. Đã chấm SQL Score cho **10/10 case** và toàn bộ Execution Score có trạng thái `UNSCORED_DATA_EGRESS`. Tổng lượt chấm có 147 Chat Completions đã đối soát và một reservation chưa có receipt. Có **0 BigQuery jobs mới** trong toàn sprint. **51 regression tests PASS**. [Điểm từng case và judge usage](<D:/Github/text_to_SQL/docs/markdown/CLINSQL_FIRST_SCORES.md>)
