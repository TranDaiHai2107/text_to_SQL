# GPT-4o mini baseline: bằng chứng về mã tái dựng

Ngày: 2026-11-19. Đối tượng là **hàng GPT-4o-mini** của Bảng 4 OmniSQL
trên BIRD dev, không phải model OmniSQL được fine-tune. Paper báo cáo
58,8% EX (Gre) và 61,5% EX (Maj). Đây là số của paper, chưa phải kết quả
chạy cục bộ.

## Mức xác nhận có thể đạt

- **Mã nguồn công khai:** 63 file trong `official/` giống từng byte với
  commit `a66d732010c89fac4353488d1c59e0b06f92b742` của tác giả.
  `evaluate_bird.py`, `infer.py` và `auto_evaluation.py` không bị sửa.
  `verify_assets.py` kiểm tra manifest SHA-256 trước khi chạy.
- **Benchmark:** BIRD `dev_20240627` có 1.534 câu và 11 SQLite database;
  archive, bản giải nén, database và prompt `data/dev_bird.json` đã được
  đối chiếu hash. Prompt là bản tiền xử lý tác giả phát hành, không phải
  prompt do chúng ta tự viết lại.
- **Adapter GPT-4o mini:** `run_gpt4o_reference.py` gửi duy nhất
  `input_seq` dưới dạng một user message. `output_seq` chứa gold SQL,
  không được gửi vào API. Model được pin bằng tên snapshot
  `gpt-4o-mini-2024-07-18`. Gre: temperature 0, một candidate. Maj:
  temperature 0,8, tám candidates. Mỗi response được lưu nguyên văn;
  `parse_sql` dùng regex lấy code block `sql` cuối cùng giống `infer.py`
  của tác giả. Cấu hình yêu cầu nằm trong hàm `request_spec`, có kiểm thử
  chống rò gold SQL.
- **Chọn SQL và chấm:** `score_bird.py` import evaluator gốc; Gre dùng
  một SQL. Maj chạy `major_voting` của tác giả theo kết quả thực thi của
  tám SQL, rồi tính EX. Wrapper chạy một lượt warm-up và một lượt ghi
  điểm như `auto_evaluation.py`.
- **Truy xuất bằng chứng:** mỗi mode lưu manifest có hash prompt, BIRD,
  adapter và evaluator cùng snapshot/model, nhiệt độ, số candidates;
  checkpoint lưu row index, hash prompt từng câu, phản hồi thô, SQL trích
  ra, tên model do API trả về và token usage. Resume từ checkpoint từ chối
  manifest hoặc câu hỏi khác.

## Phần không thể khẳng định là code tác giả

Repo công khai chỉ chứa `infer.py` cho model mở chạy qua vLLM. Tác giả
không phát hành mã gọi API GPT-4o mini hoặc phản hồi GPT-4o mini theo
từng câu. Vì vậy **không thể chứng minh adapter API giống từng dòng code**
hoặc giống mọi tham số bí mật/không công bố của họ. Cụ thể,
`max_tokens=2048` được lấy từ `infer.py` của model mở; paper không công
bố giá trị `max_tokens`, `top_p`, retry và cách đóng gói message của lần
gọi GPT-4o mini. Model API là dịch vụ đóng, nên phản hồi có thể thay đổi.

Phát biểu phù hợp trong khóa luận: **“Tái dựng baseline GPT-4o mini theo
giao thức được công bố; dùng đúng BIRD dev và evaluator tác giả; các lựa
chọn API không được công bố được ghi nhận như giả định triển khai.”**
Không dùng cụm “sao chép chính xác mã API của tác giả”.

## Trạng thái hiện tại và điều kiện hoàn tất

**Đã chạy thật ngày 2026-11-19** trên đủ 1.534 câu, server trả về đúng
`gpt-4o-mini-2024-07-18`, không response nào bị cắt. Chấm bằng evaluator
gốc với `num_cpus=4`, `timeout=60` (lý do xem AUDIT.md §2):

| Mode | Đúng / 1534 | EX | Paper | Chi phí |
|---|---|---|---|---|
| Gre | 904 | 58,93% | 58,8% | ≈ $0,71 |
| Maj (8) | 951 | 61,99% | 61,5% | ≈ $2,41 |

Lệch +0,1 và +0,5 điểm nằm trong nhiễu dự kiến của API đóng (Maj lấy mẫu ở
temperature 0,8). Kết quả ở `results/omnisql/gpt-4o-mini-2024-07-18/`.

Ghi chú quy trình: adapter đã được viết lại trong cùng ngày. Lượt chạy thật
dùng bản không ghi `input_sha256` từng dòng; căn chỉnh câu hỏi được bảo đảm
bằng `row_index` và việc `score_bird.py` so `input_seq` với prompt đã pin.
Manifest được dựng lại sau lượt chạy với cấu hình giống hệt manifest dry-run
ban đầu (chỉ hash evaluator đổi do chuyển CRLF về LF, nội dung không đổi).
Các lượt chạy mới ghi `input_sha256` cho từng dòng.

Kế hoạch bên dưới vẫn áp dụng cho bước so sánh với Ours.

Trước khi chạy thật: đóng băng commit, prompt và metric; thử kết nối API
bằng một mẫu ngoài BIRD dev; sau đó chạy Gre và Maj mỗi cấu hình một lần
trên toàn bộ dev. Lưu manifest, checkpoint, prediction JSON, selected SQL,
EX từng câu và chi phí. Không chọn ngưỡng/prompt dựa trên BIRD dev.
Để chứng minh đóng góp của **Ours**, chạy cùng snapshot GPT-4o mini trên
cùng 1.534 câu cho cả baseline tái dựng và Ours, chấm cùng evaluator,
đối chiếu theo từng câu; số 58,8%/61,5% từ paper là mốc tham khảo ngoài.

Nguồn: [paper OmniSQL](https://www.vldb.org/pvldb/vol18/p4695-li.pdf),
[source công khai](https://github.com/RUCKBReasoning/OmniSQL),
[model GPT-4o mini](https://developers.openai.com/api/docs/models/gpt-4o-mini).

## Phân tích độ lệch so với paper (2026-11-19, không gọi API)

Tác giả không phát hành prediction GPT-4o-mini, nên chỉ phân tích được nguồn nhiễu phía mình.
Dữ liệu: `results/omnisql/gpt-4o-mini-2024-07-18/baseline_sample_analysis.json`. Mỗi SQL greedy, mỗi
SQL trong 8 mẫu và mỗi gold đều được thực thi lại và đo thời gian. Bộ tái lập này cho đúng 904 / 951,
khớp evaluator.

| Nguồn | Kết quả đo | Ảnh hưởng |
|---|---|---|
| Thứ tự 8 mẫu (`max()` lấy nhóm gặp trước khi hòa phiếu) | 66 câu hòa nhóm đầu, trong đó 37 câu thứ tự quyết định đúng/sai; xáo thứ tự 300 lần cho Maj 61,47–62,58 (sd 0,20) | Đủ giải thích 61,5 vs 62,0 |
| Nhiễu lấy mẫu T=0,8 (bootstrap 8 mẫu, 300 lần) | Maj trung bình 61,18, sd 0,39, khoảng 95% 60,30–61,93 | Paper 61,5 nằm trong khoảng; bản của mình ở đuôi trên |
| `random.choice` khi cả 8 mẫu lỗi (không đặt seed) | 8 câu, không mẫu nào đúng | 0 |
| Timeout (60 s so với 10 s của tác giả) | Không câu greedy đúng nào chạy quá 10 s; Maj với ngưỡng 10 s hoặc 5 s vẫn 951 | 0 |
| Greedy T=0 | Lệch 2 câu (904 so với ≈902) | Nằm trong độ bất định của API đóng ở T=0; cần chạy lại mới đo được |
