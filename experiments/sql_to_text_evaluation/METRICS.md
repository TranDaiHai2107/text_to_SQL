# Bộ chấm đầu ra tiếng Anh độc lập

Phiên bản: `english_reference_v1`. Chương trình: `english_metrics.py`.
Đây là phần mở rộng riêng; không thay metric, gold hoặc kết quả Text-to-SQL cũ.
Nhãn tham chiếu tiếng Anh được render từ kết quả SQL chuẩn bằng quy tắc xác định,
không phải nhãn ngôn ngữ tự nhiên chính thức do EHRSQL công bố hoặc bác sĩ duyệt.

## Quy ước và mẫu số

- Input tham chiếu: các bản ghi `id`, `output_text`, `answerable`, `result_rows`.
- Prediction: `id → output_text`, hoặc danh sách bản ghi có cùng hai trường.
- ID phải khớp chính xác: thiếu, thừa hoặc trùng ID dừng chấm. Muốn ghi nhận một
  lần sinh thất bại, cung cấp chuỗi rỗng cho ID đó; câu đó vẫn nằm trong mẫu số.
- Loader chặn key JSON trùng ngay khi đọc JSON/JSONL, trước khi Python có thể
  giữ giá trị cuối và làm mất dấu bản ghi đầu. Quy tắc áp dụng cả ID mapping
  và field trùng bên trong một record.
- Mọi điểm tổng hợp đều nhân 100. EM, F1, ROUGE-L và fact-EM càng cao càng tốt.
  WER càng thấp càng tốt và không bị giới hạn ở 100.
- Báo cáo tổng hợp toàn tập và riêng `answerable` / `unanswerable`. Điểm cao nhờ
  lặp lại cùng câu từ chối không được dùng thay cho độ chính xác câu trả lời.
- Chuẩn hóa lexical: Unicode NFKC, casefold, tách theo khoảng trắng. Giữ nguyên
  dấu câu, số, dấu âm/dương, thập phân, từ phủ định và mạo từ. Đây là cấu hình
  công khai của bộ chấm này, không mặc nhiên tương đương tokenizer của thư viện
  hoặc số điểm ở một bài báo khác.

## Chỉ số về cách diễn đạt

Gọi `r_i` là dãy token tham chiếu và `p_i` là dãy token dự đoán của câu i;
`N` là số câu. Không có stemmer hoặc mô hình ngôn ngữ trong các công thức sau.

1. **raw_EM**: `100 × Σ[reference_text_i = predicted_text_i] / N`, so sánh chuỗi
   gốc; **normalized_EM** dùng hai dãy token sau chuẩn hóa ở trên.
2. **token_F1_macro**: với mỗi câu, đếm giao đa tập token
   `M_i = Σ_t min(count_r_i(t), count_p_i(t))`, rồi lấy
   `100 × mean(2M_i / (len(r_i) + len(p_i)))`. Token lặp lại được tính đúng số lần.
   **token_F1_micro** gộp tử và mẫu của toàn tập trước khi chia. Khi cả hai dãy
   rỗng thì F1 của cặp đó bằng 1; nếu chỉ một dãy rỗng thì F1 bằng 0.
3. **ROUGE_L_F1_macro**: thay `M_i` trong F1 bằng độ dài dãy con chung dài nhất
   `LCS(r_i,p_i)`, rồi lấy trung bình theo câu. Thuật toán này giữ thứ tự token
   và dùng F1 đối xứng. Cơ sở ROUGE-L là công trình
   [Chin-Yew Lin, 2004 — ROUGE: A Package for Automatic Evaluation of Summaries](https://aclanthology.org/W04-1013/).
   Đây là bản triển khai LCS với tokenizer nêu trên, không gọi ROUGE package
   chính thức và không tự nhận điểm số tương đương cấu hình stemming/tokenization khác.
4. **WER**: `100 × Σ_i edit_distance(r_i,p_i) / Σ_i len(r_i)`, khoảng cách
   Levenshtein token với chi phí thay/thêm/xóa mỗi token bằng 1. Đây là WER
   gộp toàn corpus, không phải trung bình WER từng câu. Công thức và giới hạn
   về đánh giá nội dung được trình bày tại
   [Hugging Face Evaluate — WER metric card](https://huggingface.co/spaces/evaluate-metric/wer/blob/main/README.md).
   Thêm nhiều token có thể làm WER vượt 100. Nếu tổng token tham chiếu bằng 0,
   WER bằng 0 khi không có lỗi, còn có token thêm thì trả `null` vì mẫu số bằng 0.

Các chỉ số này đo độ giống cách viết. Ví dụ đổi “3” thành “4”, hoặc bỏ một từ
“not”, có thể vẫn giữ F1 rất cao trong khi câu trả lời sai. Một cách diễn đạt
khác nhưng đúng cũng có thể nhận điểm lexical thấp. Không dùng lexical score
để khẳng định tính đúng lâm sàng hoặc làm ngưỡng lọc SQL.

## Chỉ số về kết quả: controlled fact-EM

`controlled.fact_EM = 100 × số câu có dữ kiện khớp chính xác / N`.

- Chỉ trích xuất dữ kiện từ **chuỗi tiếng Anh prediction** qua parser của
  `reference_renderer.py`. Trường `result_rows` do prediction tự khai không
  được dùng để chứng minh câu trả lời đúng.
- Reference trong chế độ controlled cũng phải parse được và diễn đạt đúng
  `answerable`/`result_rows` của chính nó. Mâu thuẫn ở gold dừng chấm; lỗi của
  prediction nhận 0 và vẫn nằm trong mẫu số. `--lexical-only` vẫn cho phép
  reference viết bằng tiếng Anh tự do.
- Hai câu từ chối phải cùng trạng thái không trả lời được. SQL `NULL` trong
  một ô, kết quả rỗng, lỗi thực thi và câu hỏi không trả lời được là các tình
  huống khác nhau.
- Với câu trả lời được, so sánh toàn bộ các hàng sau chuẩn hóa numeric3
  (làm tròn 3 chữ số thập phân) và sắp xếp hàng. Giữ thứ tự cột, hàng trùng và
  SQL `NULL`; không cắt ở 100 hàng. Đây là quy ước toàn kết quả của phần mở rộng,
  khác cap 100 hàng của official SQL scorer. Không thay đổi scorer cũ.
- Thiếu/thêm hàng hoặc ô, đổi số, thay cột, hoặc từ chối sai đều thất bại.
  JSON lỗi, prose thừa/đối nghịch và chuỗi ngoài grammar được ghi nhận
  không parse được, nhận 0 điểm cho metric này, không bị loại khỏi mẫu số.
- **parse_coverage**: `100 × số prediction parse được / N`, luôn báo cùng
  fact-EM. Một câu tiếng Anh tự do đúng có thể không parse được; fact-EM ở đây
  chỉ xác nhận định dạng tiếng Anh có kiểm soát, không phải semantic evaluator
  cho mọi văn bản hoặc metric đã công bố của ProbGate.

Grammar yêu cầu cách viết canonical của renderer, gồm chính xác số đã chuẩn
hóa (`"3.0"` thay vì `"3"`) và thứ tự dòng đã sắp xếp. Một giá trị tương đương
viết khác định dạng vẫn không parse được. Vì vậy fact-EM là kiểm tra định dạng
kiểm soát và dữ kiện cùng lúc, không phải semantic equivalence cho mọi cách viết.

Nếu dùng lại cùng renderer cho gold và prediction, phép đo này kiểm tra việc
bảo toàn kết quả qua bước SQL → text. Nó không chứng minh một mô hình tự sinh
diễn giải y khoa đúng, và không tạo ra kết quả SQL → text đã công bố của paper.

## Chưa đưa vào điểm chính

BLEU/SacreBLEU và BERTScore chưa được tính trong phiên bản này. Khi cần thêm,
phải cố định package, tokenizer/model, phiên bản và cấu hình, đồng thời vẫn
kiểm tra sai số, phủ định và dữ kiện. Không điền các cột chưa chạy bằng 0 hoặc
gọi các metric bổ sung đó là thẩm định chuyên gia.

## Chạy

```powershell
.venv\Scripts\python.exe experiments/sql_to_text_evaluation/english_metrics.py `
  --references experiments/sql_to_text_evaluation/data/references/test.jsonl `
  --predictions path/to/predictions.json `
  --output path/to/english_scores.json
```

Với văn bản tiếng Anh tự do, có thể dùng `--lexical-only` để không áp dụng
parser controlled-English. Kết quả khi đó chỉ có độ giống từ ngữ; không có
con số factual correctness tự động.
