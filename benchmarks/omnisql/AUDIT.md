# Kiểm toán tái hiện OmniSQL trên BIRD dev

Ngày kiểm toán: 2026-11-19. Phạm vi: source OmniSQL tại `benchmarks/omnisql/official`,
BIRD `dev_20240627`, prompt BIRD do tác giả tiền xử lý, evaluator EX của tác giả,
và một lượt chạy lại thật baseline `gpt-4o-mini-2024-07-18`.

## Kết luận

1. **Dữ liệu, prompt và source trùng khớp với bản tác giả công bố.** Source giống
   từng byte với GitHub tại commit đã ghim. BIRD dev và prompt khớp hash.
2. **Cách chấm tái hiện chính xác.** Đưa file dự đoán tác giả công bố qua evaluator
   gốc của họ cho ra **đúng 6/6 con số EX trong paper** (OmniSQL 7B/14B/32B, greedy
   và majority). Warm-up và lượt ghi điểm cho cùng kết quả.
3. **Baseline GPT-4o-mini được dựng lại đúng.** Chạy lại thật trên cả 1.534 câu:
   greedy **58,9** (paper 58,8) và majority-8 **62,0** (paper 61,5).

Chưa làm: chạy lại trọng số OmniSQL (cần GPU, máy này chỉ có RTX 3050 4 GB), tái
huấn luyện SynSQL-2.5M, và tích hợp Ours vào BIRD.

## 1. Source, dữ liệu, prompt

- **Source:** `RUCKBReasoning/OmniSQL`, commit `a66d732010c89fac4353488d1c59e0b06f92b742`.
  - Cả 63 file trong `official/` đã được so với `raw.githubusercontent.com` tại commit
    này và **giống từng byte**.
  - Bản checkout Windows trước đó có CRLF ở 59 file. Lỗi này đã sửa bằng cách ghi lại
    đúng byte upstream (LF). `.gitattributes` đặt `benchmarks/omnisql/official/** -text`
    để Git không đổi xuống dòng trên bất kỳ hệ điều hành nào.
  - Hash trong `source_files_sha256.json` và `SOURCE_LOCK.json` là hash của byte upstream.
- **BIRD dev:** `dev.zip` từ host chính thức của BIRD, SHA-256 `cdd6d19f…a630`.
  Có 1.534 câu và 11 database SQLite. Hash từng database nằm trong `bird_db_sha256.json`.
- **Prompt:** `data/dev_bird.json` trong `OmniSQL-datasets` của tác giả, Hugging Face
  revision `e1db8bb1…`, SHA-256 `65186bb8…5b50`.
  - Cả 1.534 câu hỏi và SQL gold khớp đúng thứ tự với BIRD dev.
  - `output_seq` chứa SQL gold. Runner chỉ gửi `input_seq` cho model.
- **Dự đoán tác giả công bố:** ZIP SHA-256 `4319fb35…3cd2`.
  - Mỗi model có 1.534 record. Prompt và gold giống bản đã ghim.
  - Regex trích SQL áp lên 41.418 response cho 0 sai khác so với `pred_sqls` tác giả đã công bố.

`verify_assets.py` kiểm tra toàn bộ các hash trên trước mỗi lần chấm.

## 2. Evaluator và tham số thời gian

`score_bird.py` và `audit_paper_scores.py` import nguyên `official/train_and_evaluate/evaluate_bird.py`.
Evaluator làm như sau:
- chạy SQL dự đoán và SQL gold trên cùng database SQLite;
- so `set(rows)`, nên bỏ qua thứ tự dòng và dòng trùng, còn thứ tự cột vẫn phải khớp;
- không dùng LLM;
- chạy hai lượt như `auto_evaluation.py`: một lượt warm-up, một lượt ghi điểm.

**Tham số thời gian.** Mặc định của tác giả là 20 process và 10 giây cho mỗi cặp SQL
dự đoán + gold. Cấu hình này phụ thuộc phần cứng.
- Trên laptop 12 luồng này, các truy vấn nặng bị timeout. Kết quả là OmniSQL-7B greedy
  chỉ được 62,3–63,8 thay vì 63,9.
- Đo thời gian SQL gold trên cả 1.534 câu (4 process). Chỉ 4 câu chạy quá 5 giây:
  - q701: 891 giây
  - q518: 178 giây
  - q646: 17,5 giây
  - q596: 9,4 giây
- Không câu nào nằm trong khoảng 20–170 giây.
- Với timeout 120 giây, q518 nằm sát ngưỡng và bị lật kết quả giữa các lần chạy
  (lệch 1 câu ở majority 7B/14B).
- **Chốt `num_cpus=4`, `timeout=60` giây.** Ở ngưỡng này q646 luôn chạy kịp, còn q518
  và q701 luôn bị timeout, giống với timeout 10 giây trên server của tác giả.

Hai tham số này được truyền vào hàm gốc, không sửa file của tác giả.

Riêng bước bầu chọn trong `major_voting()`, code gốc gán cứng 20 process / 10 giây.
`score_bird.py` thay hàm `execute_sqls_parallel` lúc chạy để bước này dùng cùng giới hạn
4 process / 60 giây. Logic bầu chọn và file gốc không đổi.

## 3. Chấm lại dự đoán của tác giả

Môi trường: Windows 11, Python 3.12.4, SQLite 3.45.3, `num_cpus=4`, `timeout=60`.
Lệnh chạy: `audit_paper_scores.py`, không gọi API.

| Model | Chế độ | Đúng / 1534 | EX (%) | Paper (%) |
|---|---|---|---|---|
| OmniSQL-7B | greedy | 980 | 63,89 | 63,9 |
| OmniSQL-14B | greedy | 985 | 64,21 | 64,2 |
| OmniSQL-32B | greedy | 989 | 64,47 | 64,5 |
| OmniSQL-7B | majority (SQL tác giả đã bầu) | 1014 | 66,10 | 66,1 |
| OmniSQL-14B | majority (SQL tác giả đã bầu) | 1011 | 65,91 | 65,9 |
| OmniSQL-32B | majority (SQL tác giả đã bầu) | 1028 | 67,01 | 67,0 |

Ở mọi dòng, warm-up bằng lượt ghi điểm, và SQL được chọn khớp 100% với bản tác giả công bố.

## 4. Chạy lại thật baseline GPT-4o-mini

Tác giả không công bố code gọi API cho các model GPT. `run_gpt4o_reference.py` là bản
tái dựng, được ghi nhãn rõ, dùng đúng các thành phần sau của tác giả:
- prompt `input_seq`, gửi như một user message duy nhất;
- quy tắc trích SQL: lấy khối ```` ```sql ```` cuối cùng;
- cách sinh: greedy dùng temperature 0, n=1; majority dùng temperature 0.8, n=8;
- `max_tokens=2048`, như `max_output_len` trong `infer.py`.

Kết quả với snapshot `gpt-4o-mini-2024-07-18` (server trả về đúng snapshot này):

| Chế độ | Đúng / 1534 | EX (%) | Paper (%) | Chênh lệch |
|---|---|---|---|---|
| greedy | 904 | 58,93 | 58,8 | +0,1 điểm (khoảng 2 câu) |
| majority-8 | 951 | 61,99 | 61,5 | +0,5 điểm (khoảng 8 câu) |

- Không response nào bị cắt (`finish_reason` = `stop` ở tất cả).
- Token sử dụng:
  - greedy: 3,12 triệu vào, 0,40 triệu ra, khoảng $0,71;
  - majority: 3,12 triệu vào, 3,24 triệu ra, khoảng $2,41.
- Kết quả lưu ở `results/omnisql/gpt-4o-mini-2024-07-18/` (bị Git ignore), gồm response
  thô, `system_fingerprint`, usage, và điểm của từng câu.

API OpenAI không tất định tuyệt đối, kể cả ở temperature 0. Majority lại lấy mẫu ở
temperature 0.8. Vì vậy mức lệch +0,1 và +0,5 điểm là nằm trong độ nhiễu dự kiến, và
không thể có số trùng tuyệt đối với paper. Paper cũng không ghi `seed` hay
`system_fingerprint`.

## 5. Ranh giới và cách báo cáo

- `official/` là source gốc của tác giả.
- `score_bird.py`, `audit_paper_scores.py`, `run_gpt4o_reference.py`, `run_official_model.py`
  là wrapper do repo này viết, không phải code của tác giả.
- Khi báo cáo, cần ghi: BIRD dev `dev_20240627`, evaluator OmniSQL commit `a66d7320`,
  `num_cpus=4`, `timeout=60` giây, warm-up rồi ghi điểm.
- Mọi phương pháp so sánh với nhau (kể cả Ours) phải được chấm bằng cùng cấu hình này.
- Chưa chạy trọng số OmniSQL qua vLLM. Cần GPU khoảng 16 GB trở lên.
- BIRD là benchmark đa miền, không phải MIMIC-IV.

## Lệnh kiểm tra

```powershell
$env:PYTHONUTF8='1'
.\.venv_bird\Scripts\python.exe benchmarks/omnisql/verify_assets.py
.\.venv_bird\Scripts\python.exe benchmarks/omnisql/audit_paper_scores.py --model 7B --mode greedy_search
.\.venv_bird\Scripts\python.exe benchmarks/omnisql/audit_paper_scores.py --model 7B --mode released_majority
.\.venv_bird\Scripts\python.exe benchmarks/omnisql/score_bird.py results/omnisql/gpt-4o-mini-2024-07-18/greedy_search.json --mode greedy_search --output results/omnisql/gpt-4o-mini-2024-07-18/greedy_search_score.json
```

Nguồn: [paper PVLDB](https://www.vldb.org/pvldb/vol18/p4695-li.pdf),
[arXiv Table 4](https://arxiv.org/html/2503.02240v2),
[repo OmniSQL](https://github.com/RUCKBReasoning/OmniSQL).
