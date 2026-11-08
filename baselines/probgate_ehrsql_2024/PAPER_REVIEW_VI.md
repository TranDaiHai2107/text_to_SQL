# Paper đối chiếu hiện tại — ProbGate

Đọc lại toàn văn 10 trang ngày 06/11/2026, gồm Sections 1–5, Limitations, Ethics, tài liệu tham khảo và Appendices A–B; đối chiếu source pin và kết quả cache trong workspace. Đây là bản diễn giải/kiểm tra, không thay thế PDF gốc.

## Thông tin định danh

- Tên: **ProbGate at EHRSQL 2024: Enhancing SQL Query Generation Accuracy through Probabilistic Threshold Filtering and Error Handling**.
- Tác giả: Sangryul Kim, Donghee Han, Sehyun Kim; các đơn vị thuộc KAIST.
- Công bố: Proceedings of the 6th Clinical Natural Language Processing Workshop, ClinicalNLP 2024, trang 687–696, ACL; Mexico City, Mexico. PDF ghi ngày 21/06/2024.
- [Trang ACL](https://aclanthology.org/2024.clinicalnlp-1.65/), [PDF đầy đủ](https://aclanthology.org/2024.clinicalnlp-1.65.pdf), [DOI](https://doi.org/10.18653/v1/2024.clinicalnlp-1.65), [arXiv](https://arxiv.org/abs/2404.16659).
- [Repository tác giả](https://github.com/venzino-han/probgate_ehrsql); commit cục bộ `2dcc2230ea049e7fb87160df922933b4ae2645b9`.
- Folder: `baselines/probgate_ehrsql_2024/`. `upstream/` là source tác giả, `data/` là inputs/gold, `configs/` là cấu hình và điểm công bố, `runs/audit_20261023_docker/` là kết quả replay cache.

## Bài toán và đóng góp

Paper giải quyết **English question → SQL hoặc null** trên EHRSQL 2024. Mục tiêu là trả lời có chọn lọc: query chạy được nhưng sai vẫn nguy hiểm; câu không đủ thông tin nên từ chối. Các nền tảng trong Section 2 là Text-to-SQL/schema awareness và token confidence. Đóng góp thực nghiệm tập trung vào bộ lọc confidence kết hợp execution, không phải một bộ sinh câu trả lời hội thoại tiếng Anh.

## Dữ liệu: paper và snapshot đang dùng

Paper dùng EHRSQL 2024 trên **MIMIC-IV demo**, có thêm câu hỏi không thể trả lời. Nguồn câu hỏi EHRSQL gốc được thu thập từ 222 nhân sự bệnh viện; điều này không có nghĩa từng câu trả lời tiếng Anh tự sinh của dự án được bác sĩ phê duyệt.

Các số sau đã đối chiếu với dataset local của tác giả/official annotation:

- Train: 5.124 = 4.674 answerable + 450 unanswerable.
- Validation/dev: 1.163 = 931 + 232.
- Test: 1.167 = 934 + 233.
- Tổng: 7.454; database snapshot 17 bảng. Mốc thời gian trong postprocessor là `2100-12-31 23:59:00`.

Paper nêu trực tiếp train/test; chi tiết partition dev, thời gian và chuẩn hóa ở trên là thông tin đã kiểm tra từ artifact cục bộ, không gán thành trích dẫn nguyên văn paper. Các câu unanswerable bao gồm thông tin không có trong schema hoặc cần kiến thức ngoài database. Test có loại unanswerable khác train.

## Pipeline chính (Figure 2; Sections 3.3–3.5)

1. Bỏ 450 câu null khỏi train; fine-tune **gpt-3.5-turbo-0125** trên 4.674 cặp question–SQL answerable.
2. Prompt hướng model trả đúng SQL thuần, tránh bọc toàn bộ query bằng dấu nháy hoặc thêm giải thích.
3. Sinh SQL và lấy log-probability token.
4. **ProbGate:** bỏ các token nằm trong danh sách reserved words; lấy các log-prob thấp nhất còn lại, trung bình làm confidence mỗi query.
5. Xếp các query theo confidence; nhóm thấp nhất được chuyển thành null theo ngưỡng rank.
6. **GEF:** thực thi SQL còn lại trên database; câu bị lỗi chuyển thành null để tránh phạt trả lời sai. Helper public còn lọc kết quả rỗng, chi tiết rộng hơn mô tả lỗi ngữ pháp trong paper.

Trong notebook public, số token thấp nhất là `bottom_n=10`. Các ngưỡng `387/450/425` là tham số lọc **giữa các câu hỏi/query**, không phải token budget, xác suất0.425 hay số token thấp nhất. Code dùng rank zero-based và điều kiện `<=`; ties có thể làm số câu bị lọc khác một con số ngưỡng đơn giản. Không áp425 như một ngưỡng phổ quát cho dataset khác hoặc online từng câu.

Inference notebook dùng temperature0, logprobs=True, top_logprobs=5. Đây là đối chiếu source; paper không pin đầy đủ mọi prompt/hyperparameter/checkpoint. Không có RAG ba nguồn hoặc ba nhánh DeepSeek như V6 trong pipeline ProbGate chính.

## Metric và cách hiểu

`RS(c) = 100 × (C − c×W) / N`.

- C: SQL trả kết quả đúng **hoặc** từ chối đúng câu unanswerable.
- W: trả SQL sai cho câu answerable **hoặc** cố trả lời câu unanswerable.
- Từ chối câu answerable: 0 điểm, vẫn giữ trong mẫu số.
- Các penalty: c=0,5,10,N. Mốc xếp hạng chính là RS10.
- Điểm âm lớn là hợp lệ. RS0 không đồng nghĩa EX trên answerable, và RS10 không phải phần trăm câu trả lời đúng thuần.

Official scorer trong workspace so kết quả thực thi với chuẩn hóa số3 chữ số và sắp/cap100 dòng; không so exact string SQL. Helper raw của tác giả có khác biệt numeric/string; xem `UPSTREAM_NOTES.md`.

## Tất cả thí nghiệm Table 1 — dev

Mỗi dòng theo thứ tự RS0 / RS5 / RS10 / RSN (điểm công bố):

1. T5-small FT + Filtering: **47.81 / 45.66 / 43.51 / −452.19**.
2. T5-Large-text2sql-spider FT + Filtering: **74.63 / 59.59 / 44.54 / −3425.37**.
3. T5-Large-text2sql-spider FT + Classifier(T5): **63.80 / 18.23 / −27.34 / −10536.20**.
4. T5-Large-text2sql-spider FT + Filtering + Classifier(T5): **72.74 / 58.56 / 44.37 / −3227.26**.
5. GPT FT + Classifier(T5): **90.28 / 51.59 / 12.89 / −8109.02**.
6. GPT FT + Classifier(GPT): **88.05 / 57.95 / 27.86 / −6911.95**.
7. GPT FT + ProbGate(387): **85.30 / 80.57 / 75.84 / −1014.70**.

Filtering ở các nhánh T5 là entropy filtering; Classifier là bộ phân loại answerable/unanswerable. Không cộng entropy, classifier và ProbGate thành pipeline cuối duy nhất: đó là các nhánh so sánh/ablation. Dev75.84 không phải test74.21.

## Tất cả thí nghiệm Table 2 — test

Cùng thứ tự RS0 / RS5 / RS10 / RSN:

1. GPT FT: **73.52 / −58.87 / −191.25 / −30826.47**.
2. GPT FT + ProbGate(450): **79.43 / 73.01 / 66.58 / −1420.57**.
3. GPT FT + ProbGate(450) + GEF: **79.78 / 75.92 / 72.06 / −820.22**.
4. GPT FT + ProbGate(425) + GEF: **81.92 / 78.06 / 74.21 / −818.08**.

Cấu hình cuối là mốc so với V6. Paper kết thúc shared task ở hạng3. Xếp hạng này thuộc cuộc thi2024, không phải bảng xếp hạng mọi hệ thống Text-to-SQL hiện nay.

## Phân tích Figure 3 và các phụ lục

Figure3 so phân phối confidence giữa model fine-tuned và unfine-tuned. Paper mô tả chia train70/30 cho **phân tích này**: train70% answerable để FT, infer phần30% gồm cả hai loại. Tác giả nhận thấy confidence phân tách answerable/unanswerable rõ hơn sau FT. Không áp phép chia này lên toàn bộ các bảng khác. Code preprocessing public dùng90/10 ở chỗ khác; chưa đủ artifact để tái tạo chính xác Figure3.

AppendixA là reserved-word list để bỏ khỏi phép tính confidence. AppendixB là JSON messages với system prompt, user question, assistant goldSQL dùng cho fine-tuning. Không cung cấp bộ gold câu trả lời tiếng Anh hội thoại để chấm WER/ROUGE.

## Giới hạn paper tự nêu và giới hạn source

- Threshold nhạy với dataset và phân phối unanswerable; tối ưu RS10 trong setting cuộc thi có thể khó chuyển miền.
- Phụ thuộc GPT fine-tuned đóng; cần nghiên cứu thêm model mở và phát hiện unanswerable ngoài phân phối.
- Ethics đề cập bias, harmful output và nguy cơ dữ liệu nhạy cảm khi fine-tune/API; không tuyên bố đã được kiểm định triển khai lâm sàng.
- Source không có checkpoint T5 generator/classifier; fine-tuned GPT ID thuộc tài khoản tác giả, không truy cập được chỉ bằng API key của mình.
- Một số prompt bị gán đè và config/hyperparameters không đủ pin từng thí nghiệm. Chỉ có đủ cache để replay bốn nhánh test; không thể nói đã train lại mọi11 nhánh.

Các thiếu hụt và khác biệt code/paper có bằng chứng ở `MODELS.md`, `UPSTREAM_NOTES.md`, `source_manifest.json` và `FINAL_RUN_REVIEW.md`.

## So sánh với hệ thống hiện tại V6

Số liệu **đo và audit trong workspace**, tách khỏi số paper:

- V6 DeepSeek Flash: RS0=92.97; RS5=83.98; RS10=74.98; RSN=−2007.03; EX=92.40%; VSR=75.75%. SQL đúng863, từ chối đúng222, sai21, từ chối nhầm61.
- Cache ProbGate cuối: SQL đúng726, từ chối đúng230, sai9, từ chối nhầm202. EX tính bổ sung77.73%; VSR62.98%. Hai số này không phải cột paper công bố.
- Chênh RS10 chưa làm tròn: **+0.771208 điểm**. V6 trả lời được nhiều câu đúng hơn, nhưng paper ít câu trả lời sai hơn và RSN tốt hơn. Không kết luận V6 tốt hơn ở mọi tiêu chí.
- V6 không fine-tune; dùng train+dev làm knowledge và ba nhánh generation có ngân sách khác. Paper fine-tune GPT trên train answerable. Khác model/compute/knowledge nên đây là đối chiếu kết quả hệ thống, chưa cô lập ưu thế phương pháp.
- Test cũ đã được quan sát khi phát triển. Việc chỉ giữ tên V6 không xóa exposure hoặc tạo holdout độc lập.
- English→SQL→English của V6 đạt controlled fact-EM92.97%, WER14.29% bằng renderer theo mẫu và reference tự xây. Paper không công bố phép đánh giá đó; không mang điểm này so với RS hoặc gọi gold English chính thức của paper.

## Đường dẫn sử dụng

Hệ thống hiện tại: `experiments/ours_improved_v6/current.py`; kết quả: `experiments/ours_improved_v6/runs/reviewed_20261101_once/FINAL_RESULTS.json`.

Source paper/database/gold giữ ở folder này. Các phiên bản đề xuất cũ và nghiên cứu đã bỏ nằm trong `_archive/20261106/`; chỉ được dùng làm provenance/runtime kế thừa, không phải phiên bản hiện tại.
