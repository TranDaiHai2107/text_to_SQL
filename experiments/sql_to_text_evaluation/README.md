# Kết quả chốt và bộ đánh giá câu trả lời tiếng Anh

Phần mở rộng ngày 01/11/2026, tách hoàn toàn khỏi V5, Vanna, database và official scorer Text-to-SQL. Không đổi model, không gọi API, không dùng nhãn mới để sửa pipeline hoặc tăng điểm SQL.

## Kết quả Text-to-SQL hiện tại

Fresh replay đủ 1.167 câu test, gồm 934 câu có đáp án và 233 câu không thể trả lời; khớp từng kết quả chấm đã lưu:

- **V5 / DeepSeek Flash**: RS0=92,89; RS5=83,89; **RS10=74,89**; RSN=−2007,11; EX=92,29%; VSR=75,66%. SQL đúng 862; từ chối đúng 222; trả lời sai 21; từ chối nhầm 62.
- **Vanna / DeepSeek Flash**: RS0=85,00; RS5=13,45; **RS10=−58,10**; RSN=−16615,00; EX=85,87%; VSR=82,86%. SQL đúng 802; từ chối đúng 190; trả lời sai 167; từ chối nhầm 8.
- **Vanna + GEF / cùng generation DeepSeek Flash**: RS0=86,46; RS5=37,19; **RS10=−12,08**; RSN=−11413,54; EX=85,87%; VSR=78,58%. SQL đúng 802; từ chối đúng 207; trả lời sai 115; từ chối nhầm 43.
- **ProbGate / prediction tác giả phát hành**: RS0=81,92; RS5=78,06; **RS10=74,21**; RSN=−818,08; EX=77,73%; VSR=62,98%. SQL đúng 726; từ chối đúng 230; trả lời sai 9; từ chối nhầm 202.

RS là metric bài báo. EX là tỷ lệ SQL trả kết quả đúng trên **934 câu có đáp án**; VSR là SQL thực thi thành công trên **toàn bộ 1.167 câu**, không đồng nghĩa nội dung đúng. EX/VSR của paper được tính thêm từ cache prediction, không phải hai cột công bố trong paper. Đây là replay cache, chưa huấn luyện/chạy lại model tác giả.

V5 hơn paper khoảng 0,69 điểm RS10 quan sát, nhưng paper ít câu trả lời sai hơn và RSN tốt hơn. V5 đã phát triển sau nhiều lần xem test; model, knowledge và ngân sách inference giữa các hệ thống chưa bằng nhau. Khoảng tin cậy đã lưu cho chênh RS10 chứa 0. Chưa thể dùng các số này để khẳng định phương pháp vượt trội độc lập.

Xem [đối chiếu chi tiết](results/TEXT_TO_SQL_COMPARISON_VI.md) và [số liệu/hash](results/TEXT_TO_SQL_COMPARISON.json).

## Bộ dữ liệu tiếng Anh đã thêm

Người dùng xác nhận **output là câu trả lời chứa kết quả SQL**, không phải câu mô tả ý nghĩa truy vấn. Bản mở rộng có tên `EHRSQL2024-derived-controlled-English-v1` và giữ nguyên membership của cả ba split:

- `train`: **5.124** câu, gồm 4.674 có đáp án và 450 không thể trả lời.
- `validation`: **1.163** câu, gồm 931 có đáp án và 232 không thể trả lời. Đây là split `dev` gốc, chỉ đổi tên trong bản xuất mới.
- `test`: **1.167** câu, gồm 934 có đáp án và 233 không thể trả lời.
- Tổng: **7.454** cặp có thêm trường/cột `output_text`.

File JSONL và CSV nằm trong `data/references/`. Mỗi dòng giữ `id`, `input_text`, `input_sql`, SQL đã thay thời gian cố định, gold answer gốc, kết quả đầy đủ `result_rows`, `output_text`, split, phương pháp và trạng thái nhãn. CSV thêm cột trong **bản sao mở rộng**, không sửa dataset gốc. Hash nguồn, code và từng file xuất nằm trong `data/MANIFEST.json`.

Đây là **nhãn tham chiếu tự động theo mẫu, suy ra từ benchmark gốc**, không phải nhãn tiếng Anh chính thức do tác giả EHRSQL cung cấp, cũng chưa được bác sĩ/người chấm độc lập kiểm định.

## Cách gán nhãn

1. Đối chiếu ID và tính answerable giữa question, gold SQL và gold execution answer.
2. Thực thi gold SQL read-only trên đúng SQLite gốc, dùng postprocessing gốc và mốc `2100-12-31 23:59:00`.
3. So kết quả với gold theo numeric3 và giới hạn 100 dòng của bộ chấm gốc. Mismatch dừng, không tự sửa gold hoặc bịa nhãn.
4. Lưu **toàn bộ dòng** cho nhãn tiếng Anh, chuẩn hóa số theo 3 chữ số thập phân, giữ thứ tự cột và dòng trùng; sắp dòng để có biểu diễn ổn định. Không khẳng định thứ hạng theo thứ tự dòng.
5. Render câu tiếng Anh bằng grammar cố định và kiểm tra giải mã trả lại đúng các giá trị. Không gọi LLM để suy đoán nội dung lâm sàng.

Ví dụ thật ở test: câu hỏi về organism của bệnh nhân 10027602 có kết quả `enterococcus sp.` được gán:

> The returned value is "enterococcus sp.".

Kết quả số được giữ dưới dạng giá trị trích dẫn, chẳng hạn `The returned value is "4721.95".`; không tự đoán loại tiền tệ, đơn vị, chuyển tỷ lệ thành phần trăm hay đổi 0/1 thành khẳng định lâm sàng Yes/No. Danh sách được xuất thành các dòng `Row 1: ["..."]` trong câu trả lời tiếng Anh có kiểm soát. Đây là hạn chế có chủ ý: bảo toàn dữ liệu, chưa đánh giá độ tự nhiên của văn phong.

Ba trạng thái khác nhau:

- Không thể trả lời theo gold: `This question cannot be answered using the available database.`
- SQL hợp lệ nhưng không có dòng: `The query returned no rows.`
- SQL NULL trong một ô: `The returned value is null.`

Lỗi SQL của hệ thống là lỗi, không được đổi thành từ chối đúng. `answer_from_sql.py` dùng một câu lỗi riêng.

## Hai phép đánh giá cần tách

**SQL → câu trả lời tiếng Anh:** dùng `data/sql_to_text_inputs/{split}.jsonl`, có question, gold SQL và kết quả truy vấn để kiểm tra riêng verbalizer. Việc cung cấp gold SQL/results chỉ hợp lệ cho phép đánh giá thành phần này. So câu hệ thống sinh với `data/references/{split}.jsonl`.

**Tiếng Anh → tiếng Anh toàn hệ thống:** chỉ đưa `data/inputs/{split}.jsonl` chứa ID và câu hỏi vào hệ thống. Hệ thống tự sinh SQL, chạy database, tạo câu trả lời; sau đó scorer mới đọc reference. Không đưa gold SQL, gold result, output_text test vào model/RAG. Điểm cuối bao gồm cả lỗi truy vấn lẫn lỗi diễn đạt.

Mặc dù người dùng trước đó dùng train+dev làm knowledge cho V5, reference test mới chỉ phục vụ chấm. Chưa có code nào tự động thêm nhãn tiếng Anh mới vào knowledge hoặc thay cấu hình V5. Muốn tuning bộ sinh tiếng Anh nên giữ validation riêng; không dùng điểm test để thử đến lúc cao.

## Chỉ số mới

`english_metrics.py` xuất **Exact Match**, **token F1**, **ROUGE-L F1**, **WER** cùng số mẫu, mẫu số, per-question và nhóm answerable/unanswerable riêng. WER càng thấp càng tốt; có thể vượt 100%. Đây là phép đo khác từ vựng, không phải bằng chứng câu trả lời đúng về mặt y khoa. WER vốn thường dùng cho ASR; với câu trả lời có nhiều cách diễn đạt, chỉ dùng bổ trợ.

Với đúng grammar kiểm soát, **controlled fact EM** giải mã giá trị **từ chính output text** rồi so toàn bộ rows, cột, số lần lặp và trạng thái từ chối với reference. Luôn báo thêm parse coverage. Metric này là metric tự xây của phần mở rộng, không phải metric chính thức EHRSQL. Một câu diễn đạt tự do có thể đúng nhưng không parse được; dùng `--lexical-only` để chỉ đo lexical khi chưa có validator cho văn phong đó.

Không gọi tự so reference với chính nó là kết quả mô hình. Cũng không lấy điểm English mới gán cho paper: paper ProbGate không cung cấp đối chứng bộ sinh câu trả lời cho phần này. Xem [định nghĩa metric](METRICS.md).

## Audit và khả năng tái lập

- `audit_source.py`: audit toàn bộ SQL và execution answer nguồn, không đọc nhãn tiếng Anh để suy ra đáp án.
- `audit_references.py`: kiểm tra nhãn bằng parser độc lập, thực thi lại SQL, đối chiếu đầy đủ dòng/cột/lặp, CSV, ID, input không chứa gold, hash và nguồn không đổi.
- Tests bao gồm sửa số, phủ định/thêm claim, thiếu/trùng dòng, hơn 100 dòng, SQL NULL, empty, từ chối, ID thiếu, và SQL bị lỗi/ghi database.

Audit phát hiện **44 câu** trả hơn 100 dòng (train 32, validation 5, test 7), nhiều nhất **152** dòng. Nhãn tiếng Anh giữ đủ; official Text-to-SQL vẫn cap 100 như cũ. SQL `DENSE_RANK` có thể trả nhiều hơn số top-k trong câu hỏi khi đồng hạng: không được tự cắt xuống k. Có **75** query chứa dòng kết quả trùng và **1** kết quả rỗng hợp lệ trong validation.

Các kiểm tra máy xác nhận độ trung thành với kết quả SQL theo quy ước đã nêu, không chứng minh gold SQL trả lời đúng mọi ý nghĩa câu hỏi hay mức hiểu lâm sàng. Muốn gọi nhãn là human/clinician gold cần vòng kiểm định độc lập; audit tự động nhiều lần không thay đổi trạng thái này.

Trạng thái bàn giao: source audit và independent reference audit đều pass; 7.454/7.454 nhãn bảo toàn dữ kiện theo parser độc lập; toàn bộ tests và self-check scorer trên cả ba split pass. Xem `REFERENCE_AUDIT.json` và `results/DELIVERY_VALIDATION.json`. Self-check scorer dùng oracle chỉ để kiểm tra phần mềm, **không phải điểm sinh tiếng Anh của V5/Vanna**. Chưa gọi lại các hệ thống để tạo câu trả lời tiếng Anh tự do.

Vòng audit thêm bằng ba agent độc lập đã xác nhận lại số liệu và nhãn, tìm và sửa hai lỗi tiếp nhận đầu vào của scorer (JSON trùng key và gold text mâu thuẫn structured result). Chi tiết và bằng chứng sau sửa: [tổng hợp audit 01/11/2026](audits/20261101/AUDIT_SUMMARY_VI.md).

## Chạy tại project root

```powershell
# Tái tạo cả 7.454 nhãn; không API.
python experiments/sql_to_text_evaluation/build_references.py

# Đối soát nhãn độc lập và nguồn.
python experiments/sql_to_text_evaluation/audit_source.py
python experiments/sql_to_text_evaluation/audit_references.py

# Kiểm tra hash, chạy tests và self-check scorer trên cả ba split.
# Self-check không phải điểm mô hình; báo cáo ghi rõ phân biệt này.
python experiments/sql_to_text_evaluation/validate_delivery.py

# Chấm output tiếng Anh của hệ thống, ID phải đủ và khớp chính xác.
python experiments/sql_to_text_evaluation/english_metrics.py --references experiments/sql_to_text_evaluation/data/references/test.jsonl --predictions path/to/system_english_outputs.jsonl --output experiments/sql_to_text_evaluation/results/system_english_scores.json

# Tùy chọn: renderer không LLM dùng SQL prediction đã có; đây là đối chứng template chung.
python experiments/sql_to_text_evaluation/answer_from_sql.py --sql-predictions experiments/ours_improved_v5/runs/deepseek_flash_v5_20261029_r1/test/v5_selected.prediction.json --output experiments/sql_to_text_evaluation/results/v5_template_english.jsonl

# Đối chiếu lại điểm SQL cũ; không chạy model.
python experiments/sql_to_text_evaluation/compare_frozen_results.py
```

Prediction JSONL tối thiểu: `{"id":"ID gốc","output_text":"Câu trả lời của hệ thống"}`. Có thể dùng JSON mapping ID→text. Không tự bỏ các câu thiếu; scorer dừng khi thiếu/thừa/trùng ID. Output lỗi có thể là chuỗi rỗng để tính như failure, giữ nguyên mẫu số.

## Nguồn nghiên cứu

- [ProbGate at EHRSQL 2024](https://aclanthology.org/2024.clinicalnlp-1.65/): paper so sánh English→SQL, các điểm RS.
- [Dataset EHRSQL 2024](https://github.com/glee4810/ehrsql-2024): question, SQL, execution answer; commit gốc đã pin trong `baselines/probgate_ehrsql_2024/source_manifest.json`.
- [ROUGE, Lin 2004](https://aclanthology.org/W04-1013/): họ metric lexical; implementation mới ghi rõ tokenizer riêng, không tuyên bố giống một package ROUGE cụ thể.
- [WER metric card](https://huggingface.co/spaces/evaluate-metric/wer/blob/main/README.md): Levenshtein theo từ và công thức WER; không phải metric độ đúng lâm sàng.
