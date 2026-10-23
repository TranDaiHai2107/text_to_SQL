# Bài báo được tái hiện

**ProbGate at EHRSQL 2024: Enhancing SQL Query Generation Accuracy through Probabilistic Threshold Filtering and Error Handling**

- Tác giả: Sangryul Kim, Donghee Han, Sehyun Kim.
- Hội nghị/workshop: Proceedings of the 6th Clinical Natural Language Processing Workshop, 2024, trang 687–696.
- Trang chính thức: https://aclanthology.org/2024.clinicalnlp-1.65/
- PDF: https://aclanthology.org/2024.clinicalnlp-1.65.pdf
- DOI: https://doi.org/10.18653/v1/2024.clinicalnlp-1.65
- ArXiv: https://arxiv.org/abs/2404.16659
- Source: https://github.com/venzino-han/probgate_ehrsql

## Phạm vi cấu hình

Không chỉ cấu hình cuối đạt 81.92/74.21: thư mục có đủ 11 cấu hình trong hai bảng đánh giá chính. Điểm công bố đầy đủ và đường dẫn source cho từng dòng nằm ở `configs/experiments.json`.

Table 1, dev:

Các điểm sau được chép từ **Table 1, trang in 692 / trang PDF 6**, theo thứ tự **RS(0) / RS(5) / RS(10) / RS(N)**, trên thang điểm nhân 100:

1. T5-small FT + Filtering: **47.81 / 45.66 / 43.51 / -452.19**.
2. T5-Large-text2sql-spider FT + Filtering: **74.63 / 59.59 / 44.54 / -3425.37**.
3. T5-Large-text2sql-spider FT + Classifier(T5): **63.80 / 18.23 / -27.34 / -10536.20**.
4. T5-Large-text2sql-spider FT + Filtering + Classifier(T5): **72.74 / 58.56 / 44.37 / -3227.26**.
5. gpt-3.5-turbo FT + Classifier(T5): **90.28 / 51.59 / 12.89 / -8109.02**.
6. gpt-3.5-turbo FT + Classifier(gpt-3.5-turbo): **88.05 / 57.95 / 27.86 / -6911.95**.
7. gpt-3.5-turbo FT + ProbGate(t=387): **85.30 / 80.57 / 75.84 / -1014.70**.

Table 2, test:

Nguồn **Table 2, cùng trang**, cùng thứ tự **RS(0) / RS(5) / RS(10) / RS(N)**:

1. gpt-3.5-turbo FT: **73.52 / -58.87 / -191.25 / -30826.47**.
2. gpt-3.5-turbo FT + ProbGate(t=450): **79.43 / 73.01 / 66.58 / -1420.57**.
3. gpt-3.5-turbo FT + ProbGate(t=450) + GEF: **79.78 / 75.92 / 72.06 / -820.22**.
4. gpt-3.5-turbo FT + ProbGate(t=425) + GEF: **81.92 / 78.06 / 74.21 / -818.08**.

**Đây là kết quả công bố của tác giả, chưa phải kết quả đã chạy lại trong workspace.** Số 90.28 ở dev không được dùng làm điểm test. Cấu hình test cuối là mốc 81.92 RS(0) và 74.21 RS(10), không được gọi hai số này là EX.

## Đọc chỉ số và mức cải thiện trong bài

- FT: fine-tuning; GEF: Grammatical Errors Filtering.
- RS(c) thưởng +1 cho trả lời đúng hoặc từ chối đúng câu unanswerable, phạt -c cho trả lời sai, và cho 0 khi từ chối câu answerable. Điểm được lấy trung bình và nhân 100.
- Các mức c ở bảng là 0, 5, 10 và N (số câu trong split). Do có phạt, RS có thể âm rất lớn; đó không phải lỗi phần trăm.
- Trong Table 2, cấu hình cuối so với GPT FT đơn thuần tăng **8.40 điểm RS(0)** và **265.46 điểm RS(10)**. Đây là hiệu số điểm, không phải phần trăm tăng tương đối.
- Chỉ so số liệu của mình với các mốc này khi cùng split, database, annotation và scorer. Folder đã giữ source scorer của tác giả và tách chế độ chuẩn hóa EHRSQL riêng; tái lập điểm vẫn thuộc bước chạy sau.

[Đối chiếu nguồn PDF, Table 1–2](https://aclanthology.org/2024.clinicalnlp-1.65.pdf).

## Kết quả chạy lại ngày 23/10/2026

Đã replay đủ bốn nhánh test bằng cache tác giả và database pin ở trên. Official scorer cho RS0 lần lượt **73.52 / 79.43 / 79.78 / 81.92**, cấu hình cuối RS10 **74.21**. Một số ô khác có sai khác hiển thị 0.01 điểm; giá trị thực và số công bố được giữ riêng. Helper raw trong repo tác giả phân biệt số/chuỗi số ở hai câu nên không dùng làm protocol chính. Chi tiết và đường dẫn evidence: [FINAL_RUN_REVIEW.md](FINAL_RUN_REVIEW.md). Đây là cache replay, chưa phải huấn luyện/inference lại model hoặc kết quả hệ thống RAG của ứng dụng.

## Dataset đang dùng trong dự án có so trực tiếp được không?

Kết quả kiểm tra hiện tại: **giữ MIMIC-IV Mini và 180 câu nội bộ để phát triển; dùng dataset riêng của ProbGate khi so sánh với bài báo**. Chi tiết schema, split, rủi ro overlap và kế hoạch áp dụng: [DATASET_REVIEW.md](DATASET_REVIEW.md).

Figure 3 là phân tích phân phối logprob cho GPT fine-tuned/unfine-tuned, không phải một dòng baseline có điểm RS. Source không kèm đủ artifact của cả hai nhánh để vẽ lại chính xác. Paper mô tả split train 70/30 ở phân tích này, trong khi script preprocessing công khai dùng 90/10; không tự gán split của Figure 3 cho tất cả baseline.

## Citation

```bibtex
@inproceedings{kim-etal-2024-probgate,
  title = {{ProbGate} at {EHRSQL} 2024: Enhancing SQL Query Generation Accuracy through Probabilistic Threshold Filtering and Error Handling},
  author = {Kim, Sangryul and Han, Donghee and Kim, Sehyun},
  booktitle = {Proceedings of the 6th Clinical Natural Language Processing Workshop},
  year = {2024},
  pages = {687--696},
  publisher = {Association for Computational Linguistics},
  url = {https://aclanthology.org/2024.clinicalnlp-1.65/}
}
```
