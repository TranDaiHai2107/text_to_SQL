# Metric không cần ground truth cho luồng Việt → Anh → SQL → Anh → Việt

Ngày: 2026-11-19. File này chỉ khảo sát metric, không sửa code nào.

## 1. Bài toán cần đánh giá

```
(A) Câu hỏi tiếng Việt ──dịch──▶ câu hỏi tiếng Anh
(B) Câu hỏi tiếng Anh ──text-to-SQL──▶ SQL ──chạy──▶ kết quả (1 giá trị, 1 dòng hoặc 1 bảng)
(C) Kết quả + câu hỏi tiếng Anh ──sinh văn bản──▶ câu trả lời tiếng Anh
(D) Câu trả lời tiếng Anh ──dịch──▶ câu trả lời tiếng Việt
```

Phần B đã được đánh giá bằng benchmark có gold (BIRD, EX). Ba phần cần metric **không cần đáp án mẫu** là:

| Phần | Đầu vào để chấm | Đầu ra cần chấm | Loại bài toán trong tài liệu |
|---|---|---|---|
| A | Câu hỏi tiếng Việt | Bản dịch tiếng Anh | Machine Translation Quality Estimation (QE) |
| C | Câu hỏi tiếng Anh + bảng kết quả SQL | Câu trả lời tiếng Anh | Data-to-text / table-to-text, đánh giá không tham chiếu |
| D | Câu trả lời tiếng Anh | Bản dịch tiếng Việt | MT Quality Estimation (QE) |

Tiêu chí chọn metric:
1. Không cần đáp án mẫu.
2. Được dùng nhiều trong paper uy tín (WMT, ACL, EMNLP, NAACL, TACL).
3. Có code hoặc checkpoint công khai để chạy lại.
4. Áp dụng được cho tiếng Việt (phần A, D) hoặc cho dữ liệu bảng (phần C).

## 2. Phần A và D: dịch Việt ↔ Anh (Quality Estimation)

Tất cả metric dưới đây chỉ cần **câu nguồn + bản dịch**, không cần bản dịch mẫu.

| Metric | Nguồn | Cách hoạt động | Điểm | Tiếng Việt | Chạy lại | Ghi chú |
|---|---|---|---|---|---|---|
| **COMETKiwi-22** (`Unbabel/wmt22-cometkiwi-da`) | Rei et al., WMT 2022 (hạng nhất QE shared task 2022) | Encoder InfoXLM/XLM-R đọc cặp (nguồn, bản dịch), hồi quy ra điểm chất lượng do người chấm (DA) | 0–1 | Có (XLM-R hỗ trợ tiếng Việt) | `pip install unbabel-comet`, khoảng 0,5B tham số, chạy được trên GPU 8 GB | **Đề xuất làm metric chính.** Phổ biến nhất trong các paper MT 2023–2025. Giấy phép CC BY-NC-SA (phi thương mại, dùng cho khóa luận được) |
| **COMETKiwi-23 XL / XXL** | Rei et al., WMT 2023 (hạng nhất QE 2023) | Như trên, encoder XLM-R XL (3,5B) / XXL (10,7B) | 0–1 | Có | XL cần ≥ 15 GB GPU | Mạnh hơn nhưng nặng. Dùng nếu có GPU lớn |
| **MetricX-24 (chế độ QE)** (`google/metricx-24-hybrid-*-v2p6`) | Juraska et al., WMT 2024 | mT5 hồi quy; cùng một mô hình chạy được cả khi có và không có tham chiếu | 0–25 (càng thấp càng tốt) | Có (mT5) | Code `google-research/metricx`; có các cỡ Large, XL, XXL; giấy phép Apache 2.0 | **Đề xuất làm metric thứ hai** để đối chiếu, vì khác họ mô hình với COMET |
| **xCOMET-XL / XXL (chế độ QE)** | Guerreiro et al., TACL 2024 | Vừa cho điểm vừa đánh dấu các đoạn lỗi (nhẹ / nặng / nghiêm trọng); bỏ tham chiếu thì thành QE | 0–1 kèm danh sách lỗi | Có | `unbabel-comet` | Hữu ích khi phân tích lỗi: chỉ ra được đoạn dịch sai |
| **GEMBA-MQM / GEMBA-DA** | Kocmi & Federmann, EAMT 2023 và WMT 2023 | Dùng LLM (GPT-4…) làm người chấm: đếm lỗi theo khung MQM hoặc chấm điểm 0–100 | Điểm MQM hoặc 0–100 | Có | Prompt công khai (`microsoft/gemba`) | Cần API. **Không dùng cùng LLM vừa dịch vừa chấm**, vì LLM có xu hướng ưu ái câu do chính nó sinh |

**Nên kèm theo một kiểm tra quy tắc riêng cho bài toán:** các con số, ngày tháng, đơn vị, tên riêng và mã (ví dụ mã bệnh, tên thuốc) trong câu nguồn phải xuất hiện đủ và đúng trong bản dịch. Đây là lỗi nguy hiểm nhất với hệ hỏi đáp dữ liệu, và metric QE tổng quát đôi khi chấm nhẹ loại lỗi này. Kiểm tra này đơn giản, tự cài đặt được, và nên báo cáo dưới dạng tỉ lệ câu bảo toàn đủ thực thể.

Không đề xuất các metric sau làm metric chính:
- **BLEU/chrF trên bản dịch ngược (round-trip):** bản dịch sai vẫn có thể dịch ngược ra câu gần giống câu gốc. Chỉ nên dùng làm thông tin phụ.
- **BLASER 2.0-QE** (Meta, SONAR): có trong WMT 2023 nhưng ít được dùng hơn COMETKiwi và MetricX.

## 3. Phần C: kết quả SQL → câu trả lời tiếng Anh

Câu trả lời được chấm theo ba khía cạnh, và chỉ cần **bảng kết quả + câu hỏi**:
- **Trung thực với dữ liệu (faithfulness):** không bịa số, không sai giá trị.
- **Đầy đủ (coverage):** không bỏ sót thông tin trong kết quả.
- **Đúng trọng tâm câu hỏi (relevance):** trả lời đúng điều được hỏi.

| Metric | Nguồn | Đo gì | Cách hoạt động | Chạy lại | Ghi chú |
|---|---|---|---|---|---|
| **Data-QuestEval** | Rebuffel et al., EMNLP 2021 | Trung thực + đầy đủ | Sinh câu hỏi từ bảng rồi trả lời bằng văn bản, và sinh câu hỏi từ văn bản rồi trả lời bằng bảng; so khớp hai chiều | Code trong `ThomasScialom/QuestEval` (chế độ data-to-text) | **Metric data-to-text không tham chiếu kinh điển.** Hạn chế: huấn luyện trên dữ liệu kiểu WebNLG; thư viện cũ, phải cố định phiên bản; với bảng nhiều số thì có domain shift. Cần chuyển bảng SQL thành bộ ba (dòng, cột, giá trị) |
| **Đánh giá bằng NLI hai chiều** | Dušek & Kasner, INLG 2020 | Bịa thông tin (hallucination) và bỏ sót (omission) | Mỗi ô hoặc mỗi dòng của bảng được viết thành câu ngắn: văn bản phải suy ra được từng câu này (không bỏ sót), và từng câu của văn bản phải được bảng hỗ trợ (không bịa) | Chỉ cần một mô hình NLI công khai (ví dụ RoBERTa/DeBERTa-MNLI) | Dễ cài đặt lại, dễ giải thích. Rất hợp với kết quả SQL vì bảng thường nhỏ |
| **AlignScore** | Zha et al., ACL 2023 | Nhất quán sự kiện giữa ngữ cảnh và văn bản | RoBERTa huấn luyện trên 4,7 triệu mẫu từ 7 loại tác vụ; ngữ cảnh ở đây là bảng đã chuyển thành văn bản | `yuh-zha/AlignScore`, có checkpoint | Metric factual consistency mạnh và phổ biến 2023–2025. Cần thử xem chuyển bảng thành văn bản theo cách nào cho điểm ổn định |
| **Slot Error Rate (SER) / độ phủ giá trị** | Dušek, Novikova & Rieser, Computer Speech & Language 2020 (đánh giá E2E NLG Challenge) | Tỉ lệ giá trị trong dữ liệu bị thiếu, sai hoặc thừa trong văn bản | Đối chiếu bằng quy tắc: mỗi giá trị trong kết quả SQL (số, tên) có xuất hiện đúng trong câu trả lời không; mỗi con số trong câu trả lời có trong kết quả không | Tự cài đặt (so khớp chuỗi và số có chuẩn hóa) | **Đề xuất bắt buộc** vì kết quả SQL có giá trị rõ ràng. Rẻ, chính xác, dễ giải thích. Với bảng lớn mà câu trả lời chỉ tóm tắt thì đo độ chính xác (precision) là chính |
| **G-Eval** | Liu et al., EMNLP 2023 | Các tiêu chí tùy chọn: trung thực, đầy đủ, liên quan, trôi chảy | LLM chấm theo tiêu chí có chain-of-thought, lấy trung bình có trọng số theo xác suất điểm | Prompt công khai; cần API | Phổ biến nhất cho kiểu "LLM làm giám khảo". Không cho mô hình đang được chọn tự chấm chính nó |
| **Prometheus 2** | Kim et al., EMNLP 2024 | Như G-Eval, theo rubric | LLM mở (7B, 8x7B) được huấn luyện riêng để chấm theo rubric | Checkpoint công khai, chạy local | Thay thế G-Eval nếu muốn **không phụ thuộc API** và tránh thiên vị cùng họ mô hình |
| **RAGAS: Faithfulness + Answer Relevancy** | Es et al., EACL 2024 (demo) | Trung thực với ngữ cảnh; mức liên quan của câu trả lời với câu hỏi | Faithfulness: tách câu trả lời thành các mệnh đề rồi kiểm tra từng mệnh đề với ngữ cảnh. Relevancy: sinh lại câu hỏi từ câu trả lời rồi so độ tương đồng với câu hỏi gốc | Thư viện `ragas` | Coi kết quả SQL là "ngữ cảnh truy hồi". Được dùng rất nhiều trong các paper hỏi đáp có ngữ cảnh. Answer Relevancy là phần mà các metric data-to-text khác không đo |

**Gợi ý tổ hợp cho phần C:**
- **SER / độ phủ giá trị:** kiểm tra cứng về số liệu.
- **NLI hai chiều hoặc AlignScore:** đo trung thực bằng mô hình nhỏ, chạy được local.
- **RAGAS Answer Relevancy hoặc G-Eval tiêu chí "relevance":** đo việc trả lời đúng câu hỏi.
- **Data-QuestEval:** báo cáo thêm để đối chiếu với các paper data-to-text.

## 4. Quy trình chọn mô hình bằng các metric này

1. **Tập thử:** lấy câu hỏi tiếng Việt thật trong phạm vi bài toán, khoảng **300–500 câu**, chia đều theo loại kết quả (một giá trị, một dòng, nhiều dòng). Với khoảng 300 câu, so sánh ghép cặp phát hiện được chênh lệch cỡ 1–2 điểm COMETKiwi. Ít hơn 100 câu thì khoảng tin cậy quá rộng.
2. **Cố định đầu vào cho từng phần:**
   - Phần A: mọi mô hình dịch cùng một bộ câu hỏi tiếng Việt.
   - Phần C: mọi mô hình nhận cùng một bộ (câu hỏi tiếng Anh, kết quả SQL), để lỗi của phần trước không ảnh hưởng.
   - Phần D: mọi mô hình dịch cùng một bộ câu trả lời tiếng Anh.
3. **Chọn mô hình:** theo trung bình metric. Báo cáo kèm **khoảng tin cậy bootstrap ghép cặp** (paired bootstrap resampling, Koehn, EMNLP 2004). Hai mô hình có khoảng tin cậy chồng nhau thì coi là ngang nhau; khi đó chọn mô hình rẻ hoặc nhanh hơn.
4. **Dùng ít nhất hai metric khác họ** (ví dụ COMETKiwi và MetricX-QE cho dịch; SER và AlignScore cho phần C). Mô hình thắng ở cả hai metric thì kết luận chắc chắn hơn.
5. **Tránh thiên vị giám khảo:** không để LLM giám khảo cùng họ với mô hình được chấm. Nghiên cứu cho thấy LLM có xu hướng ưu ái văn bản do chính nó sinh (Panickssery et al., NeurIPS 2024).
6. **Kiểm chứng metric bằng một mẫu nhỏ có người chấm,** khoảng 50–100 câu mỗi phần: tính tương quan (Kendall hoặc Spearman) giữa metric và đánh giá của người. Bước này trả lời câu hỏi của hội đồng: "metric này có đáng tin cho tiếng Việt và cho miền dữ liệu của em không?" Lý do cần bước này: COMETKiwi và MetricX được huấn luyện chủ yếu trên các cặp ngôn ngữ của WMT, còn với Việt–Anh thì chúng chạy theo kiểu zero-shot qua bộ mã hóa đa ngôn ngữ.

## 5. Tóm tắt đề xuất

| Phần | Metric chính | Metric đối chiếu | Kiểm tra quy tắc |
|---|---|---|---|
| A: Việt → Anh (câu hỏi) | COMETKiwi-22 (hoặc 23-XL) | MetricX-24 QE; xCOMET-QE để phân tích lỗi | Bảo toàn số, ngày, tên, mã |
| C: kết quả SQL → câu trả lời tiếng Anh | NLI hai chiều hoặc AlignScore (trung thực) + RAGAS Answer Relevancy | Data-QuestEval; G-Eval hoặc Prometheus 2 | SER / độ phủ giá trị |
| D: Anh → Việt (câu trả lời) | COMETKiwi-22 (hoặc 23-XL) | MetricX-24 QE; GEMBA-MQM (giám khảo khác họ) | Bảo toàn số, ngày, tên, mã |

## Nguồn

- COMETKiwi: Rei et al., *CometKiwi: IST-Unbabel 2022 Submission for the Quality Estimation Shared Task*, WMT 2022; Rei et al., [*Scaling up CometKiwi*](https://arxiv.org/pdf/2309.11925), WMT 2023; model card [Unbabel/wmt23-cometkiwi-da-xl](https://huggingface.co/Unbabel/wmt23-cometkiwi-da-xl).
- MetricX-24: Juraska et al., [*MetricX-24*](https://export.arxiv.org/pdf/2410.03983), WMT 2024; [google/metricx-24-hybrid-xl-v2p6](https://huggingface.co/google/metricx-24-hybrid-xl-v2p6).
- xCOMET: Guerreiro et al., *xCOMET: Transparent Machine Translation Evaluation through Fine-grained Error Detection*, TACL 2024.
- GEMBA: Kocmi & Federmann, *Large Language Models Are State-of-the-Art Evaluators of Translation Quality*, EAMT 2023; *GEMBA-MQM*, WMT 2023.
- Data-QuestEval: Rebuffel et al., [*Data-QuestEval: A Referenceless Metric for Data-to-Text Semantic Evaluation*](https://arxiv.org/abs/2104.07555), EMNLP 2021; code [ThomasScialom/QuestEval](https://github.com/ThomasScialom/QuestEval).
- NLI cho data-to-text: Dušek & Kasner, *Evaluating Semantic Accuracy of Data-to-Text Generation with Natural Language Inference*, INLG 2020.
- AlignScore: Zha et al., *AlignScore: Evaluating Factual Consistency with a Unified Alignment Function*, ACL 2023.
- SER: Dušek, Novikova & Rieser, *Evaluating the state-of-the-art of End-to-End Natural Language Generation: The E2E NLG Challenge*, Computer Speech & Language 2020.
- G-Eval: Liu et al., *G-Eval: NLG Evaluation using GPT-4 with Better Human Alignment*, EMNLP 2023.
- Prometheus 2: Kim et al., *Prometheus 2: An Open Source Language Model Specialized in Evaluating Other Language Models*, EMNLP 2024.
- RAGAS: Es et al., *RAGAS: Automated Evaluation of Retrieval Augmented Generation*, EACL 2024 (demo).
- Thiên vị tự ưu ái: Panickssery et al., *LLM Evaluators Recognize and Favor Their Own Generations*, NeurIPS 2024.
- Bootstrap ghép cặp: Koehn, *Statistical Significance Tests for Machine Translation Evaluation*, EMNLP 2004.
