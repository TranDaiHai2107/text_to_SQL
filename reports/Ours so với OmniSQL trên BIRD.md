# Ours so với OmniSQL (GPT-4o-mini) trên BIRD dev

Ngày: 2026-11-19. Mọi số liệu trong file đều do chạy thật trên máy local, trừ các dòng ghi "paper".

## 1. Tóm tắt

Cùng mô hình `gpt-4o-mini-2024-07-18`, cùng prompt gốc và cùng bộ chấm điểm của paper OmniSQL (PVLDB 2025):

| Hệ thống | Greedy (Gre) | Majority (Maj) |
|---|---|---|
| GPT-4o-mini, số paper báo cáo | 58,8 | 61,5 |
| GPT-4o-mini + prompt OmniSQL, chạy lại | 58,93 | 61,99 |
| **Ours** (gpt-4o-mini) | **60,50** | **63,62** |
| **Ours v9 đầy đủ** (17 ứng viên + selector) | — | **65,06** |

- Ours tốt hơn baseline ở cả hai chế độ.
- Ở chế độ Majority, Ours dùng đúng 8 mẫu như baseline và vẫn hơn có ý nghĩa thống kê (p = 0,012 trên held-out).
- Bản đầy đủ v9 hơn baseline 3,1 điểm (p = 0,0003), đổi lại chi phí gấp khoảng 2,7 lần.

## 2. Các khái niệm dùng trong bảng

- **BIRD dev.** Đây là bộ đánh giá text-to-SQL công khai, phiên bản 20240627. Bộ có 1534 câu hỏi tiếng Anh trên 11 cơ sở dữ liệu SQLite thật. Mỗi câu kèm một đoạn *evidence* (kiến thức bổ sung, ví dụ "eligible free rate = Free Meal Count / Enrollment") và một câu SQL đúng (gold) do người viết.
- **EX (Execution Accuracy).** Chạy câu SQL dự đoán và câu SQL gold trên cùng database. Câu được tính đúng nếu tập các dòng kết quả của hai câu bằng nhau. EX là phần trăm số câu đúng. Đây là metric chính của paper.
- **Greedy (Gre).** Mô hình sinh **1** câu SQL ở temperature 0, tức là chọn từ có xác suất cao nhất ở mỗi bước, và câu đó là đáp án.
- **Majority (Maj).** Mô hình sinh **8** câu SQL ở temperature 0,8 (có ngẫu nhiên). Chạy cả 8 câu, gom các câu cho ra cùng tập kết quả thành một nhóm, rồi chọn nhóm đông nhất. Câu nào lỗi khi chạy thì không được bỏ phiếu. Paper dùng đúng hai chế độ này cho mọi mô hình.
- **simple / moderate / challenging.** Đây là mức độ khó do tác giả BIRD gán sẵn cho từng câu. Bộ dev có 925 câu simple, 464 câu moderate và 145 câu challenging. Câu khó thường cần nhiều bảng, truy vấn lồng nhau hoặc công thức tính.
- **Tuning / held-out.** Trước khi có kết quả, 1534 câu được chia ngẫu nhiên với seed cố định 20261119 thành hai phần, lưu ở `results/omnisql/ours/splits.json`:
  - **Tuning (300 câu):** dùng để thử nghiệm và chọn thiết kế cho Ours, ví dụ có dùng selector không và đặt ngưỡng bao nhiêu.
  - **Held-out (1234 câu):** không dùng để chỉnh bất cứ thứ gì, chỉ để chấm điểm cuối.

  Nếu vừa chỉnh hệ thống vừa chấm trên cùng bộ câu, điểm sẽ cao hơn thực tế. Kết quả trên held-out mới chứng minh được cải thiện thật.
- **Kiểm định McNemar.** Hai hệ thống được so trên cùng từng câu. Chỉ những câu một bên đúng còn bên kia sai mới được tính. p < 0,05 nghĩa là chênh lệch khó có khả năng do ngẫu nhiên.

## 3. Bảng kết quả chi tiết

Bộ chấm: `evaluate_bird.py` gốc của tác giả, không sửa. Cấu hình `num_cpus=4`, `timeout=60` giây, áp dụng giống nhau cho mọi hệ thống. Lý do chọn cấu hình này nằm ở `benchmarks/omnisql/AUDIT.md`.

### 3.1. EX (%) theo tập và độ khó

| Tập | Số câu | Baseline Gre | **Ours Gre** | Baseline Maj | **Ours Maj** | **Ours v9** |
|---|---|---|---|---|---|---|
| Toàn bộ dev | 1534 | 58,93 | **60,50** | 61,99 | **63,62** | **65,06** |
| Held-out | 1234 | 58,51 | **59,89** | 61,18 | **63,37** | **64,83** |
| Tuning | 300 | 60,67 | 63,00 | 65,33 | 64,67 | 66,00 |
| Simple | 925 | 65,62 | 66,81 | 67,35 | **70,05** | **71,24** |
| Moderate | 464 | 49,78 | 51,72 | 54,96 | 54,96 | 57,11 |
| Challenging | 145 | 45,52 | 48,28 | 50,34 | 50,34 | 51,03 |

### 3.2. Kiểm định ghép cặp (McNemar chính xác)

Cách đọc cột giữa: "a / b" nghĩa là có a câu chỉ Ours đúng và b câu chỉ baseline đúng.

| So sánh | Toàn bộ dev | Held-out | Simple | Moderate | Challenging |
|---|---|---|---|---|---|
| Ours Gre so với Baseline Gre | 96 / 72, p = 0,076 | p = 0,17 | p = 0,33 | p = 0,24 | p = 0,42 |
| Ours Maj so với Baseline Maj | 83 / 58, **p = 0,043** | **p = 0,012** | **p = 0,005** | p = 1,0 | p = 1,0 |
| Ours v9 so với Baseline Maj | 105 / 58, **p = 0,0003** | **p = 0,0001** | **p = 0,0002** | p = 0,27 | p = 1,0 |

### 3.3. Chi phí (giá OpenAI cho gpt-4o-mini, toàn bộ 1534 câu)

| | Baseline Gre | Baseline Maj | Ours v9 |
|---|---|---|---|
| Số SQL ứng viên mỗi câu | 1 | 8 | 17 (+1 bản sửa lỗi nếu cần) |
| Request API trung bình mỗi câu | 1 | 1 (n = 8) | 3,2 |
| Tổng chi phí | $0,71 | $2,41 | $6,46 |
| Thời gian trung bình mỗi câu | — | — | 11,8 giây |

**Ghi chú về cột Ours Gre và Ours Maj.** Hai cột này không phải hai lần chạy riêng. Chúng được tính lại từ các ứng viên đã lưu trong lần chạy v9:
- **Ours Gre** = ứng viên greedy `g` (temperature 0). Nếu `g` lỗi hoặc trả về rỗng thì dùng bản sửa `gr`; trường hợp này xảy ra ở 98 câu.
- **Ours Maj** = bỏ phiếu trên đúng 8 mẫu `s1`–`s8` (temperature 0,8). Đây đúng là giao thức Majority-8 của paper.

Bộ chấm cục bộ cho kết quả trùng 998/998 câu với bộ chấm gốc trên lần chạy v9, nên các cột tính lại này đáng tin. Tuy vậy, khi viết khóa luận cần ghi rõ đây là "cấu hình con được tính từ cùng một lần chạy".

## 4. Hệ thống của paper: OmniSQL và baseline GPT-4o-mini

### 4.1. Paper làm gì

OmniSQL (Li et al., PVLDB 18(11), 2025) có hai đóng góp chính:
1. **SynSQL-2.5M.** Đây là quy trình tạo dữ liệu tổng hợp gồm các bước:
   - sinh database giả lập theo nhiều lĩnh vực;
   - sinh SQL theo nhiều mức độ phức tạp;
   - dịch ngược SQL thành câu hỏi tự nhiên theo nhiều văn phong;
   - sinh lời giải chain-of-thought.

   Kết quả là khoảng 2,5 triệu mẫu (database, câu hỏi, SQL, lời giải).
2. **Mô hình OmniSQL 7B/14B/32B.** Đây là Qwen2.5-Coder được fine-tune trên SynSQL cùng dữ liệu Spider và BIRD.

GPT-4o-mini, GPT-4o và GPT-4-Turbo **không được fine-tune**. Chúng chỉ là mốc tham chiếu của mô hình đóng, chạy với **cùng một prompt** như các mô hình mở. Hàng "GPT-4o-mini" trong Bảng 4 của paper chính là hệ thống được so sánh trong file này.

### 4.2. Prompt của baseline

Prompt là trường `input_seq` trong file `data/dev_bird.json` do tác giả phát hành. Đã kiểm tra hash và dùng nguyên văn. Mỗi prompt gồm:
1. **Task Overview:** "You are a data science expert… generate a valid SQL query".
2. **Database Engine:** SQLite.
3. **Database Schema:** các lệnh `CREATE TABLE` đầy đủ, mỗi cột có kiểu dữ liệu, khóa chính, khóa ngoại và một chú thích `-- example: [...]`. Các giá trị ví dụ này gồm giá trị đại diện của cột, cộng thêm các giá trị trong database khớp với chữ trong câu hỏi. Ví dụ, câu hỏi nhắc "Contra Costa" thì giá trị này được chèn vào ví dụ của cột `County Name`. Nói cách khác, baseline đã có sẵn một lớp truy hồi giá trị đơn giản.
4. **Question:** evidence của BIRD ghép trước câu hỏi.
5. **Instructions:** chỉ trả về đúng thông tin được hỏi, không thừa không thiếu, và suy nghĩ từng bước trước khi viết SQL.
6. **Output Format:** đặt SQL cuối cùng trong khối ```` ```sql ````.

### 4.3. Cách baseline chạy

- **Greedy:** 1 lời gọi API, temperature 0. Lấy khối ```` ```sql ```` cuối cùng trong câu trả lời bằng regex giống `infer.py` của tác giả.
- **Majority:** 1 lời gọi API với `n = 8`, temperature 0,8, cho ra 8 câu SQL. Hàm `major_voting()` của tác giả chạy cả 8 câu, gom theo tập kết quả và chọn nhóm đông nhất. Nếu cả 8 câu đều lỗi thì chọn ngẫu nhiên một câu.
- Không có bước sửa lỗi, không có ví dụ mẫu (few-shot), không có bước kiểm tra lại.

Tác giả không công bố code gọi API GPT. Adapter `run_gpt4o_reference.py` được dựng lại theo đúng giao thức đã mô tả: chỉ gửi `input_seq`, không bao giờ gửi SQL gold, và giữ `max_tokens = 2048` theo `infer.py`. Bản chạy lại lệch paper +0,1 điểm (Gre) và +0,5 điểm (Maj). Mức lệch này nằm trong nhiễu đo được:
- Chỉ đổi thứ tự 8 mẫu, điểm Maj đã dao động từ 61,47 đến 62,58.
- Lấy mẫu lại bằng bootstrap cho độ lệch chuẩn khoảng 0,4 điểm.

Chi tiết nằm ở `benchmarks/omnisql/GPT4O_MINI_CODE_FIDELITY.md`.

## 5. Hệ thống của tôi: Ours v9

Ours **không fine-tune** mô hình nào và dùng **cùng** gpt-4o-mini. Phần đóng góp nằm ở cách dựng ngữ cảnh, cách sinh ứng viên và cách chọn đáp án. Code chính: `src/ehrqa/bird/ours_v9.py` (dựa trên `ours_v8.py`).

### 5.1. Luồng xử lý một câu hỏi

```
Câu hỏi + evidence + database
        │
        ├─(1) Truy hồi giá trị: tìm trong database các giá trị khớp với chữ trong câu hỏi
        ├─(2) Few-shot: chọn 3 câu hỏi–SQL tương tự từ tập BIRD train (BM25)
        ▼
Prompt baseline + [giá trị đã lưu] + [3 ví dụ]     (chèn trước phần Instructions)
        │
        ├─(3a) 1 câu greedy (T=0)                         ─┐
        ├─(3b) 8 mẫu prompt baseline (T=0,8)               ├─ chạy song song
        └─(3c) 8 mẫu prompt "query plan" (T=0,8)          ─┘
        ▼
(4) Chạy cả 17 câu SQL trên SQLite
        │   nếu câu greedy lỗi hoặc trả rỗng → (5) gửi lỗi về mô hình để sửa (1 lần)
        ▼
(6) Bỏ phiếu: gom các câu có cùng TẬP kết quả, chỉ tính các câu trả về giá trị
        │
        ├─ nhóm lớn nhất chiếm ≥ 50% phiếu → chọn nhóm đó
        └─ không nhóm nào đạt đa số → (7) selector: mô hình xem tối đa 3 nhóm lớn nhất
                                         (SQL + vài dòng kết quả), suy luận từng bước,
                                         lấy 5 mẫu rồi bầu chọn
        ▼
Câu SQL cuối cùng
```

### 5.2. Từng thành phần và lý do

| # | Thành phần | Làm gì | Vì sao |
|---|---|---|---|
| 1 | Truy hồi giá trị | Chỉ mục ngược trên mọi giá trị văn bản của database (lưu cache ở `data/benchmarks/bird/ours_value_index/`). Liệt kê tối đa 12 giá trị khớp theo dạng `bảng.cột = 'giá trị'`, đúng chính tả như khi lưu | Lỗi lớn nhất của baseline là "đúng cấu trúc, sai giá trị" (236/630 câu sai). Baseline chỉ gợi ý giá trị trong chú thích của cột; Ours nêu thẳng giá trị nằm ở cột nào |
| 2 | Few-shot BM25 | 3 ví dụ từ BIRD **train** (69 database, không trùng với dev; code tự kiểm tra) | Cho mô hình xem cách viết SQL theo quy ước của BIRD (CAST AS REAL, cách đếm, cách lọc) |
| 3a, 3b | Greedy + 8 mẫu | Cùng prompt đã làm giàu ngữ cảnh | Giống giao thức Gre/Maj của paper, nhưng ngữ cảnh tốt hơn |
| 3c | Generator "query plan" | Thay phần Instructions bằng 6 bước: liệt kê đúng cột được hỏi → áp dụng evidence → bộ lọc và giá trị → join → sắp xếp/giới hạn → tự kiểm tra danh sách SELECT | Tạo **đa dạng**: một prompt khác sẽ sai theo kiểu khác. Trên tuning, số câu có ít nhất một ứng viên đúng tăng từ 217 lên 227 |
| 5 | Sửa lỗi theo thực thi | Thông báo lỗi SQLite, hoặc thông báo "kết quả rỗng", được gửi lại cho mô hình kèm câu SQL cũ | Baseline có 74 câu lỗi thực thi và 68 câu trả rỗng |
| 6 | Bỏ phiếu theo tập kết quả | Giống phép so khớp của EX: không phân biệt thứ tự dòng, không phân biệt dòng trùng | Các câu SQL chỉ khác nhau ở DISTINCT nay được gom chung một nhóm, nên phiếu không bị chia nhỏ |
| 7 | Selector có điều kiện | Chỉ gọi khi phiếu bầu không có đa số (161/1534 câu) | Thí nghiệm trên tuning cho thấy nếu gọi selector cả khi đã có đa số, gpt-4o-mini sửa được bao nhiêu câu thì làm hỏng bấy nhiêu |

Không có bước nào dùng SQL gold. Gold chỉ được dùng khi chấm điểm.

### 5.3. Đóng góp của từng phần (toàn bộ dev, đo trên cùng lần chạy v9)

| Cấu hình | EX | Ý nghĩa |
|---|---|---|
| Baseline Maj-8 | 61,99 | Mốc so sánh |
| Ours, 8 mẫu prompt baseline đã làm giàu | 63,62 | **+1,6 điểm do ngữ cảnh (giá trị + few-shot)**, cùng 8 mẫu |
| Ours, chỉ 8 mẫu prompt query plan | 62,45 | Dùng một mình thì không hơn |
| 8 baseline + 8 query plan, chỉ bỏ phiếu | 64,80 | **+1,2 điểm do đa dạng**: hai kiểu prompt bổ sung cho nhau |
| + greedy + sửa lỗi, chỉ bỏ phiếu | 64,54 | Không thay đổi đáng kể |
| + selector khi không có đa số (**v9**) | **65,06** | +0,5 điểm |
| Ours Gre: greedy + sửa lỗi | 60,50 | Sửa lỗi nâng greedy từ 58,80 lên 60,50 |

Trên tuning, ablation của v8 cho thấy riêng giá trị đã lưu hoặc riêng few-shot đều chỉ góp vài câu, nằm trong nhiễu. Hiện mới khẳng định được tác động **gộp** của hai thành phần này.

## 6. Ours tốt hơn ở đâu và chưa tốt ở đâu

**Tốt hơn:**
1. **Cùng số mẫu, vẫn hơn.** Ours Maj (8 mẫu) đạt 63,62, baseline Maj đạt 61,99. Trên held-out: 63,37 so với 61,18, p = 0,012. Đây là so sánh công bằng nhất.
2. **Bản đầy đủ hơn rõ rệt.** v9 đạt 65,06 so với 61,99 (p = 0,0003). Trên held-out: 64,83 so với 61,18 (p = 0,0001).
3. **Câu simple cải thiện mạnh nhất.** Từ 67,35 lên 71,24 (p = 0,0002). Đây đúng là nhóm lỗi "sai giá trị" và "sai số cột" mà truy hồi giá trị và prompt query plan nhắm tới.
4. **So với bảng của paper,** v9 dùng gpt-4o-mini đạt 65,06:
   - cao hơn GPT-4o của paper (61,9 Gre / 64,0 Maj), cũng như GPT-4-Turbo, DeepSeek-V3 (671B) và Qwen2.5-72B;
   - ngang greedy tốt nhất của bảng (Llama-3.1-70B, 65,1).

**Chưa tốt hơn / hạn chế:**
1. **Câu moderate và challenging** chưa có cải thiện có ý nghĩa: +2,2 điểm (p = 0,27) và +0,7 điểm (p = 1,0).
2. **Ours Gre** hơn Baseline Gre 1,6 điểm nhưng chưa có ý nghĩa thống kê (p = 0,076).
3. **v9 tốn chi phí gấp khoảng 2,7 lần** Baseline Maj và chậm hơn (khoảng 12 giây mỗi câu).
4. **Vẫn thấp hơn** Majority của các mô hình được fine-tune chuyên cho text-to-SQL (OmniSQL-7B/14B/32B: 66,1 / 65,9 / 67,0; Qwen2.5-Coder-14B/32B: 66,1 / 67,0) và Llama-3.1-70B (67,4).
5. Mỗi cấu hình **chỉ chạy một lần**. Riêng Baseline Maj dao động khoảng ±0,4 điểm giữa các lần chạy.

**Câu kết luận đề xuất cho khóa luận:**

> Không cần fine-tune, hệ thống đề xuất nâng gpt-4o-mini trên BIRD dev từ 62,0% lên 63,6% EX khi dùng cùng 8 mẫu như giao thức của OmniSQL, và lên 65,1% ở cấu hình đầy đủ (p < 0,001). Kết quả này vượt GPT-4o trong cùng bảng đánh giá. Cải thiện tập trung ở câu hỏi mức simple; với câu moderate và challenging, hai hệ thống chưa khác biệt có ý nghĩa.

## 7. Cách chạy lại

Môi trường: `.venv_bird` (`environment/requirements-omnisql-bird.txt`). Cần `OPENAI_API_KEY` trong file `.env`.

```powershell
$env:PYTHONUTF8='1'
# Chuẩn bị dữ liệu và kiểm tra hash
.\.venv_bird\Scripts\python.exe benchmarks/omnisql/download_bird_dev.py
.\.venv_bird\Scripts\python.exe benchmarks/omnisql/fetch_official_prompt.py
.\.venv_bird\Scripts\python.exe benchmarks/omnisql/fetch_bird_train.py
.\.venv_bird\Scripts\python.exe benchmarks/omnisql/verify_assets.py

# Baseline (Gre và Maj)
.\.venv_bird\Scripts\python.exe benchmarks/omnisql/run_gpt4o_reference.py --mode greedy_search --execute --max-requests 1600
.\.venv_bird\Scripts\python.exe benchmarks/omnisql/run_gpt4o_reference.py --mode major_voting --execute --max-requests 1600
.\.venv_bird\Scripts\python.exe benchmarks/omnisql/score_bird.py results/omnisql/gpt-4o-mini-2024-07-18/greedy_search.json --mode greedy_search --num-cpus 4 --timeout 60 --output results/omnisql/gpt-4o-mini-2024-07-18/greedy_search_score.json
.\.venv_bird\Scripts\python.exe benchmarks/omnisql/score_bird.py results/omnisql/gpt-4o-mini-2024-07-18/major_voting.json --mode major_voting --num-cpus 4 --timeout 60 --output results/omnisql/gpt-4o-mini-2024-07-18/major_voting_score.json

# Ours v9 (khoảng $6,5 và 45 phút với 8 luồng)
.\.venv_bird\Scripts\python.exe benchmarks/omnisql/run_ours_bird.py --variant v9 --execute --max-usd 10 --workers 8
.\.venv_bird\Scripts\python.exe benchmarks/omnisql/score_bird.py results/omnisql/ours/gpt-4o-mini-2024-07-18/v9/greedy_search.json --mode greedy_search --num-cpus 4 --timeout 60 --output results/omnisql/ours/gpt-4o-mini-2024-07-18/v9/greedy_search_score.json

# So sánh ghép cặp (toàn bộ dev, tuning, held-out, theo độ khó)
.\.venv_bird\Scripts\python.exe benchmarks/omnisql/compare_ours.py results/omnisql/ours/gpt-4o-mini-2024-07-18/v9/greedy_search_score_per_question.json
```

Thí nghiệm chọn thiết kế trên tập tuning: `benchmarks/omnisql/v9_lab.py` (các lệnh `gen`, `exec`, `eval`, `select`).

Kết quả lưu tại:
- `results/omnisql/gpt-4o-mini-2024-07-18/` (baseline);
- `results/omnisql/ours/gpt-4o-mini-2024-07-18/v9/` (Ours: predictions, traces, `comparison.json`, `candidate_executions.json`).
