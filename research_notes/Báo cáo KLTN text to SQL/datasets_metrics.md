# Bộ dữ liệu và độ đo đánh giá Text-to-SQL (BIRD là chính; Spider, Spider 2.0, EHRSQL làm bối cảnh)

Ghi chú nghiên cứu cho chương Dữ liệu và chương Đánh giá của KLTN. Ngày tra cứu: 2026-11. Mọi con số có nguồn; số kiểm tra trực tiếp trên dữ liệu cục bộ của dự án được ghi rõ "(đếm cục bộ)".

## 1. BIRD: quy mô, cấu trúc, evidence, độ khó, EX/VES, các bản sửa dev, mini-dev, leaderboard, hiệu năng con người

### Takeaway
BIRD (Li et al., NeurIPS 2023 Datasets & Benchmarks) có 12.751 cặp câu hỏi–SQL trên 95 CSDL (33,4 GB, 37 lĩnh vực), chia train 9.428 / dev 1.534 / test ẩn 1.789; EX so sánh *tập* kết quả, VES nhân thêm hệ số hiệu quả căn bậc hai tỉ số thời gian. Bản dev được dùng rộng rãi là `dev_20240627` (1.534 câu: 925 simple / 464 moderate / 145 challenging), và BIRD đã phát hành bản dev sạch hơn `dev_20251106` nên số liệu giữa hai bản không so sánh trực tiếp được.

### Cited Findings
**Thông tin thư mục**
- Jinyang Li, Binyuan Hui, Ge Qu, Jiaxi Yang, Binhua Li, Bowen Li, Bailin Wang, Bowen Qin, Rongyu Cao, Ruiying Geng, Nan Huo, Xuanhe Zhou, Chenhao Ma, Guoliang Li, Kevin C.C. Chang, Fei Huang, Reynold Cheng, Yongbin Li. "Can LLM Already Serve as A Database Interface? A BIg Bench for Large-Scale Database Grounded Text-to-SQLs." NeurIPS 2023 (Datasets and Benchmarks Track). arXiv:2305.03111 (v1 04/05/2023, v2 30/05/2023, v3 15/11/2023). — [arXiv](https://arxiv.org/abs/2305.03111)

**Quy mô**
- 12.751 cặp text-to-SQL, 95 CSDL, tổng 33,4 GB, 37 lĩnh vực chuyên môn — [arXiv abstract](https://arxiv.org/abs/2305.03111); [bird-bench.github.io](https://bird-bench.github.io/)
- Chia tập: train 9.428 câu (69 CSDL), dev 1.534 câu (11 CSDL), test ẩn 1.789 câu (15 CSDL) — [ar5iv bản HTML bài báo](https://ar5iv.labs.arxiv.org/html/2305.03111)
- Kiểm chứng cục bộ: train.json (bản phân phối trong OmniSQL-datasets) có 9.428 câu, 69 CSDL — (đếm cục bộ, `d:\Github\text_to_SQL\data\benchmarks\bird\bird_train_manifest.json`, nguồn [HF OmniSQL-datasets](https://huggingface.co/datasets/seeklhy/OmniSQL-datasets))
- Thống kê CSDL: trung bình 7,3 bảng/CSDL và 549K dòng/CSDL; nguồn CSDL 32% Kaggle, 48% CTU Prague Relational Learning Repository, 20% tự xây; CSDL lớn nhất (Donor) 4,5 GB — [ar5iv](https://ar5iv.labs.arxiv.org/html/2305.03111)

**External knowledge ("evidence")**
- Bài báo phân loại tri thức ngoài thành 4 loại: Numeric Reasoning 24,5%, Domain Knowledge 23,6%, Synonym 7,2%, Value Illustration 70,1% (tỉ lệ có chồng lấn, tổng >100%) — [ar5iv](https://ar5iv.labs.arxiv.org/html/2305.03111)
- Loại câu hỏi cơ bản: Match-based 83,9%, Counting 30,4%, Ranking 20,3%, Comparison 16,7%, Aggregation 15,7% (cũng chồng lấn) — [ar5iv](https://ar5iv.labs.arxiv.org/html/2305.03111)
- Trong `dev_20240627`, 148/1.534 câu có trường `evidence` rỗng — (đếm cục bộ, `d:\Github\text_to_SQL\data\benchmarks\bird\dev_20240627\dev.json`)

**Quy trình gán nhãn**
- 11 người bản ngữ tiếng Anh có kiến thức CSDL viết câu hỏi; chuyên gia duyệt, mỗi CSDL giữ lại khi có ≥8 câu hợp lệ; SQL do hai người gán độc lập viết (double-blind), giữ khi kết quả thực thi khớp, nếu không thì chuyên gia phân xử; 3 chuyên gia text-to-SQL toàn thời gian giám sát — [ar5iv](https://ar5iv.labs.arxiv.org/html/2305.03111)

**Độ khó (difficulty) trên dev**
- `dev_20240627`: 1.534 câu = 925 simple / 464 moderate / 145 challenging (60,3% / 30,2% / 9,5%) — (đếm cục bộ, file `dev.json` tải từ `https://bird-bench.oss-cn-beijing.aliyuncs.com/dev.zip`, sha256 `cdd6d19f…a630`, nhãn release `dev_20240627`)
- Phân bố theo CSDL (dev_20240627): card_games 191, codebase_community 186, formula_1 174, thrombosis_prediction 163, student_club 158, toxicology 145, superhero 129, european_football_2 129, financial 106, california_schools 89, debit_card_specializing 64 — (đếm cục bộ)
- Lưu ý xung đột: bản tóm tắt bài báo mà công cụ trích xuất ghi "simple 30% / moderate 60% / challenging 10%" — [ar5iv](https://ar5iv.labs.arxiv.org/html/2305.03111); dữ liệu thực tế cho thấy simple ≈60%, moderate ≈30%. Nên dẫn số đếm thực tế và kiểm tra lại bảng thống kê gốc trong PDF.
- Bộ chấm chính thức tính EX theo từng nhóm `simple/moderate/challenging` dựa trên trường `difficulty` trong file `--diff_json_path`; nhóm rỗng gây lỗi chia cho 0 — [evaluation.py chính thức](https://raw.githubusercontent.com/AlibabaResearch/DAMO-ConvAI/main/bird/llm/src/evaluation.py)

**Định nghĩa EX và VES (bài báo gốc)**
- EX = (1/N) Σₙ 𝟙(Vₙ, V̂ₙ), với 𝟙 = 1 khi tập kết quả của SQL dự đoán V̂ₙ và SQL vàng Vₙ bằng nhau, 0 nếu khác — [ar5iv](https://ar5iv.labs.arxiv.org/html/2305.03111)
- VES = (1/N) Σₙ 𝟙(Vₙ, V̂ₙ) · R(Yₙ, Ŷₙ), với R(Yₙ, Ŷₙ) = √(E(Yₙ)/E(Ŷₙ)), E là thời gian thực thi (hiệu quả tương đối của SQL dự đoán so với SQL vàng) — [ar5iv](https://ar5iv.labs.arxiv.org/html/2305.03111)
- Mã đánh giá VES (`evaluation_ves.py`): để kết quả ổn định, tác giả nâng timeout lên 3 s/ví dụ, lặp 5 lần và báo kết quả cao nhất — [repo DAMO-ConvAI/bird](https://github.com/AlibabaResearch/DAMO-ConvAI/tree/main/bird)
- Từ 04/08/2024, R-VES (Reward-based Valid Efficiency Score) thay VES làm độ đo hiệu quả cho các bài nộp test mới; điểm VES cũ được giữ cho bài nộp trước đó — [bird-bench.github.io](https://bird-bench.github.io/)

**Hiệu năng con người và mô hình (bài báo gốc)**
- Con người trên test: EX 72,37% (không tri thức) / 92,96% (có tri thức); VES 70,36% / 90,27% — [ar5iv](https://ar5iv.labs.arxiv.org/html/2305.03111). Leaderboard ghi dòng "Human Performance – Data Engineers + DB Students", Test 92,96, không có số Dev; R-VES test 83,26 — [bird-bench.github.io](https://bird-bench.github.io/)
- ChatGPT EX (không/có tri thức): dev 24,05/37,22; test 26,77/39,30. GPT-4: dev 30,90/46,35; test 34,88/54,89 — [ar5iv](https://ar5iv.labs.arxiv.org/html/2305.03111)
- Mâu thuẫn nội bộ: abstract nói ChatGPT đạt 40,08% EX, trong khi bảng cho ChatGPT test có tri thức là 39,30% (40,08 có thể là cấu hình ChatGPT + CoT hoặc phiên bản khác) — [arXiv abstract](https://arxiv.org/abs/2305.03111) vs [ar5iv](https://ar5iv.labs.arxiv.org/html/2305.03111)

**Các bản sửa dev**
- 25/09/2023: "We have released a cleaner version of dev set… We checked all cases of dev set and fixed all errors that we found." — [bird-bench.github.io](https://bird-bench.github.io/)
- `dev_20240627` là nhãn của gói dev.zip chính thức (1.534 câu, 11 CSDL SQLite); nhiều repo giải nén ra thư mục `dev_20240627` — [deeplethe/ontology2sql](https://github.com/deeplethe/ontology2sql); [manuj2002/cs646-schema-retrieval](https://github.com/manuj2002/cs646-schema-retrieval); xác nhận cục bộ qua `download_manifest.json` (release `dev_20240627`)
- 25/05/2025: BIRD thông báo sẽ "check and clean dev set (1534) for the last time during summer"; 13/11/2025: phát hành `bird-sql-dev-1106` "a cleaner development split", yêu cầu ghi rõ khi nộp để leaderboard đánh dấu — [bird-bench.github.io](https://bird-bench.github.io/)
- Thẻ dữ liệu `birdsql/bird_sql_dev_20251106` (cập nhật 06/11/2025, 1.534 dòng, split `dev_20251106`): "systematically reviewed all instances"; tinh chỉnh câu hỏi để giảm mơ hồ, sửa evidence cho ngắn gọn/chính xác, sửa SQL cho đúng cú pháp/logic và chạy được — không công bố số lượng mục bị sửa — [HF birdsql/bird_sql_dev_20251106](https://huggingface.co/datasets/birdsql/bird_sql_dev_20251106)
- Baseline EX trên Dev 1106 / Test (thẻ HF): gemini-3-pro-preview 68,97/70,43; claude-sonnet-4.5 66,56/67,02; GPT-5.1 64,02/65,96; Qwen2.5-Coder-32B-Instruct 60,95/58,36; Qwen2.5-Coder-7B-Instruct 49,22/54,11; Llama-3.1-8B-Instruct 36,70/41,08 — [HF birdsql/bird_sql_dev_20251106](https://huggingface.co/datasets/birdsql/bird_sql_dev_20251106)
- Một bài arXiv 2026 đánh giá trên `dev_20240627` và nói rõ không dùng bản dev sửa đổi để giữ khả năng so sánh — [arXiv 2606.29733](https://arxiv.org/html/2606.29733)

**BIRD Mini-Dev**
- Ra mắt 27/06/2024: 500 cặp từ 11 CSDL dev, ba phương ngữ SQLite, MySQL, PostgreSQL; phân bố 30% simple / 50% moderate / 20% challenging; bổ sung Soft-F1 và R-VES "to reduce bias" — [github.com/bird-bench/mini_dev](https://github.com/bird-bench/mini_dev); [bird-bench.github.io](https://bird-bench.github.io/)
- Soft F1: so sánh ô (cell) giữa bảng kết quả dự đoán và vàng; tp = ô khớp, fp = ô chỉ có ở dự đoán, fn = ô chỉ có ở vàng; P = tp/(tp+fp), R = tp/(tp+fn), F1 điều hòa; giảm ảnh hưởng của thứ tự cột và giá trị thiếu — [mini_dev](https://github.com/bird-bench/mini_dev)
- R-VES: thưởng theo bậc dựa trên tỉ số thời gian dự đoán/vàng thay vì tỉ số liên tục; công thức và các bậc thưởng chỉ có trong hình ảnh README — [mini_dev](https://github.com/bird-bench/mini_dev)
- GPT-4 trên mini-dev (SQLite/MySQL/PostgreSQL): EX 47,80/40,80/35,80; R-VES 45,91/39,92/35,24; Soft F1 52,69/45,78/38,96 — [mini_dev](https://github.com/bird-bench/mini_dev)
- Mini-Dev V2 (2025-07): 780 mẫu = 500 SELECT-only + 270 mẫu mới trên 18 CSDL mới (SELECT và CRUD) — [mini_dev](https://github.com/bird-bench/mini_dev)
- 28/10/2026: sửa annotation và thay một số mẫu trên cả ba phương ngữ (theo phản hồi cộng đồng + human-in-the-loop); phát hành task định dạng Harbor — [bird-bench.github.io](https://bird-bench.github.io/); [mini_dev](https://github.com/bird-bench/mini_dev)

**Leaderboard (tình trạng đến 11/2026)**
- Top EX (Dev/Test): AskData (AT&T CDO) 78,49 dev / 83,40 test, 22/10/2026; GrainSQL 77,77 dev / 82,95 test, 26/09/2026; DataGallery-Text2SQL 78,10 dev / 82,39 test, 07/09/2026; SiriusAI-SQL 77,77 dev / 82,28 test, 22/08/2026; Agentar-Scale-SQL 74,90 dev / 81,67 test, 25/09/2025. Track đơn mô hình: Gemini-SQL2 74,12 dev / 80,04 test (03/06/2026) — [bird-bench.github.io](https://bird-bench.github.io/). (Leaderboard thay đổi liên tục; ghi rõ ngày truy cập khi dẫn.)
- Bảng EX tổng có khoảng 137 dòng (đếm thủ công, xấp xỉ) — [bird-bench.github.io](https://bird-bench.github.io/)
- Hệ sinh thái mở rộng: BIRD-Critic/SWE-SQL (04/02/2025; bird-critic-1.0-postgresql 08/06/2025; BIRD-Critic-SQLite 500 issue 23/03/2026), BIRD-Interact (06/2025; bài báo 09/10/2025; ICLR 2026 Oral), LiveSQLBench (Base-Lite 270 task 29/05/2025; Base-Full-V1 600 task 09/2025; Large-v1 03/03/2026) — [bird-bench.github.io](https://bird-bench.github.io/)
- Giấy phép BIRD đổi sang CC BY-SA 4.0 — [repo DAMO-ConvAI/bird](https://github.com/AlibabaResearch/DAMO-ConvAI/tree/main/bird)

### Inferences
- Khoảng cách giữa top leaderboard (~83% test) và con người (92,96%) vẫn còn ~10 điểm, nhưng do nhiễu nhãn (mục 4) nên trần thực tế đo được bằng EX có thể thấp hơn 92,96% đáng kể trên dev.
- Khi viết KLTN phải ghi rõ phiên bản dev (`dev_20240627`), vì điểm trên `dev_20251106` không cùng thang với các bài báo 2024–2025 (OmniSQL, CHESS, …).
- Nhóm "challenging" chỉ có 145 câu: khoảng tin cậy 95% cho EX nhóm này rộng khoảng ±8 điểm (xấp xỉ nhị thức, p≈0,5), cần thận trọng khi so sánh theo độ khó.

### Gaps
- Phân bố độ khó của bản dev gốc 05/2023 (trước bản sửa 25/09/2023) và số câu bị sửa ở mỗi lần (09/2023, 06/2024, 11/2025): không tìm được nguồn chính thức nêu số lượng.
- Bảng bậc thưởng R-VES chỉ có trong ảnh README mini_dev; không trích xuất được bằng văn bản. (Theo hiểu biết chung, các bậc ≈1,25/1/0,75/0,5/0,25 theo ngưỡng tỉ số thời gian 2/1/0,5/0,25 — CHƯA kiểm chứng, không dẫn khi chưa xem ảnh.)
- Phân bố độ khó của tập test ẩn 1.789 câu: không công bố.
- Hiệu năng con người trên dev: không được báo cáo.

## 2. Spider, Spider 2.0, EHRSQL và các bộ dữ liệu bối cảnh

### Takeaway
Spider (Yu et al., EMNLP 2018) là chuẩn cross-domain kinh điển (10.181 câu, 200 CSDL, 138 lĩnh vực) với 4 mức độ khó và độ đo EM/EX, nay chính thức dùng test-suite accuracy và đã đóng leaderboard từ 05/02/2024. Spider 2.0 (Lei et al., ICLR 2025 Oral) chuyển sang quy trình doanh nghiệp, cực khó (o1-preview 21,3%); EHRSQL (Lee et al., NeurIPS 2022 D&B) là chuẩn y khoa trên MIMIC-III/eICU với câu hỏi không trả lời được — phù hợp trực tiếp cho KLTN về hỏi đáp lâm sàng.

### Cited Findings
**Spider 1.0**
- Tao Yu, Rui Zhang, Kai Yang, Michihiro Yasunaga, Dongxu Wang, Zifan Li, James Ma, Irene Li, Qingning Yao, Shanelle Roman, Zilin Zhang, Dragomir Radev. "Spider: A Large-Scale Human-Labeled Dataset for Complex and Cross-Domain Semantic Parsing and Text-to-SQL Task." EMNLP 2018 (long). arXiv:1809.08887 (24/09/2018) — [arXiv](https://arxiv.org/abs/1809.08887)
- 10.181 câu hỏi, 5.693 SQL phức tạp duy nhất, 200 CSDL nhiều bảng, 138 lĩnh vực; 11 sinh viên gán nhãn, ~1.000 giờ công — [arXiv](https://arxiv.org/abs/1809.08887); [ar5iv](https://ar5iv.labs.arxiv.org/html/1809.08887)
- Chia: train 8.659 / dev 1.034 / test 2.147 câu; theo CSDL 146 train / 20 dev / 40 test (tổng 206 ≠ 200 trong abstract, có thể do CSDL bổ sung từ các bộ cũ) — [ar5iv](https://ar5iv.labs.arxiv.org/html/1809.08887)
- 4 mức độ khó easy/medium/hard/extra hard theo số thành phần SQL, số cột chọn, số điều kiện; GROUP BY, ORDER BY, INTERSECT, truy vấn lồng, hàm gộp làm tăng độ khó — [ar5iv](https://ar5iv.labs.arxiv.org/html/1809.08887)
- Độ đo: Component Matching (F1 theo từng mệnh đề, so như tập không thứ tự), Exact Matching (mọi thành phần khớp), Execution Accuracy; baseline tốt nhất chỉ 12,4% EM ở database split — [ar5iv](https://ar5iv.labs.arxiv.org/html/1809.08887)
- Changelog: 06/07/2020 sửa lỗi annotation dev/test (~4% dev); 08/03/2020 sửa tên cột `scholar`, `formula_1`; 11/15/2020 Test Suite Accuracy thành độ đo chính thức — [github.com/taoyds/spider](https://github.com/taoyds/spider)
- Leaderboard: EX có giá trị — MiniSeek 91,2 test, DAIL-SQL + GPT-4 + Self-Consistency 86,6; EM không giá trị — MiniSeek 81,5 test / 80,3 dev; ngừng nhận bài từ 05/02/2024 — [yale-lily.github.io/spider](https://yale-lily.github.io/spider)

**Test-suite accuracy**
- Ruiqi Zhong, Tao Yu, Dan Klein. "Semantic Evaluation for Text-to-SQL with Distilled Test Suites." EMNLP 2020 (long). arXiv:2010.02840 — [arXiv](https://arxiv.org/abs/2010.02840)
- Chọn tập nhỏ CSDL từ kho lớn CSDL sinh ngẫu nhiên sao cho "code coverage" cao với SQL vàng; chấm denotation accuracy trên cả suite → cận trên chặt cho độ chính xác ngữ nghĩa. Độ đo Spider cũ có tỉ lệ false negative trung bình 2,5%, tệ nhất 8,1% trên 21 mô hình leaderboard; kiểm chứng thủ công 100 ví dụ; phát hành test suite cho 11 bộ dữ liệu — [arXiv](https://arxiv.org/abs/2010.02840)

**Spider 2.0**
- Fangyu Lei, Jixuan Chen, Yuxiao Ye, Ruisheng Cao, Dongchan Shin, Hongjin Su, Zhaoqing Suo, Hongcheng Gao, Wenjing Hu, Pengcheng Yin, Victor Zhong, Caiming Xiong, Ruoxi Sun, Qian Liu, Sida Wang, Tao Yu. "Spider 2.0: Evaluating Language Models on Real-World Enterprise Text-to-SQL Workflows." ICLR 2025 (Oral). arXiv:2411.07763 — [arXiv](https://arxiv.org/abs/2411.07763)
- 632 bài toán quy trình thực tế; CSDL thường >1.000 cột, SQL thường >100 dòng; o1-preview (khung code agent) chỉ 21,3% so với 91,2% trên Spider 1.0 và 73,0% trên BIRD — [arXiv](https://arxiv.org/abs/2411.07763)
- Biến thể hiện hành: Spider 2.0-Snow 547 ví dụ (Snowflake); Spider 2.0-Lite 547 (BigQuery 214, Snowflake 198, SQLite 135); Spider 2.0-DBT 68 task (DuckDB, từ 22/05/2025, thay setting gốc). Mốc: 24/12/2024 phát hành gold answers (ít gold SQL); 20/04/2025 phát hành ground-truth tables ("oracle tables"); 13/07/2025 sửa mơ hồ spider2-snow; 29/10/2025 sửa lỗi bộ đánh giá và cập nhật leaderboard; 12/08/2026 tài khoản Snowflake đánh giá bị tạm ngưng — [github.com/xlang-ai/Spider2](https://github.com/xlang-ai/Spider2)

**EHRSQL**
- Gyubok Lee, Hyeonji Hwang, Seongsu Bae, Yeonsu Kwon, Woncheol Shin, Seongjun Yang, Minjoon Seo, Jong-Yeup Kim, Edward Choi. "EHRSQL: A Practical Text-to-SQL Benchmark for Electronic Health Records." NeurIPS 2022 Datasets and Benchmarks Track. arXiv:2301.07695 (01/2023; v6 03/2026) — [arXiv](https://arxiv.org/abs/2301.07695)
- Câu hỏi thu từ khảo sát 222 nhân viên bệnh viện đại học (bác sĩ, điều dưỡng, bảo hiểm, hồ sơ bệnh án) → 1.742 phát biểu; 230 template (174 trả lời được, 56 không trả lời được); ~24,4K cặp (24.411; 22,5K answerable, 1,9K unanswerable); mỗi CSDL (MIMIC-III, eICU) 9,3K train / 1,1K valid / 1,8K test; câu không trả lời được chỉ ở valid/test (33% mỗi split); trung bình 13,5 bảng/CSDL, truy vấn dùng 2,4 bảng, 2,7 mức lồng, 93,2% dùng cột thời gian — [ar5iv](https://ar5iv.labs.arxiv.org/html/2301.07695)
- Độ đo: F1ans (phân biệt trả lời được) và Pexe/Rexe/F1exe (chỉ tính khi đáp án đúng); T5 + ngưỡng từ chối theo percentile: F1exe test 89,9 (MIMIC-III), 89,5 (eICU); không ngưỡng ~76–78 — [ar5iv](https://ar5iv.labs.arxiv.org/html/2301.07695)
- CSDL tiền xử lý ~95 MB (MIMIC-III), ~102 MB (eICU); trường `is_impossible`; EHRSQL trên MIMIC-IV là shared task ClinicalNLP @ NAACL 2024; v1.5.0 (09/03/2026) cải thiện chất lượng annotation (sửa SQL, độ tự nhiên câu hỏi) — [github.com/glee4810/EHRSQL](https://github.com/glee4810/EHRSQL)

### Inferences
- Với KLTN về hỏi đáp lâm sàng: BIRD có CSDL y khoa (thrombosis_prediction 163 câu, toxicology 145 câu trong dev) nhưng không có câu không trả lời được; EHRSQL bổ sung đúng khía cạnh từ chối trả lời và biểu thức thời gian — nên dùng làm bối cảnh/hướng mở rộng.
- Spider 1.0 gần bão hòa (91,2% EX) và đã đóng leaderboard, nên chỉ nên dùng làm bối cảnh lịch sử, không làm chuẩn chính.

### Gaps
- Bảng con số EX/độ khó chi tiết theo mức của Spider dev (số câu easy/medium/hard/extra): không trích xuất trong phiên này.
- Số liệu Spider 2.0-Lite/Snow mới nhất trên leaderboard (spider2-sql.github.io): chưa tra.

## 3. Cách tính EX trong bộ chấm chính thức BIRD và trong evaluate_bird.py của OmniSQL; vấn đề timeout

### Takeaway
Cả bộ chấm chính thức BIRD lẫn OmniSQL đều chấm `set(pred_rows) == set(gold_rows)`: bỏ qua thứ tự dòng và dòng trùng, nhưng phân biệt thứ tự cột và kiểu giá trị; lỗi hoặc quá thời gian đều bị tính 0. Khác biệt chính là timeout: chính thức mặc định 30 s, OmniSQL mặc định 10 s (bao trùm cả việc chạy SQL dự đoán lẫn SQL vàng).

### Cited Findings
- Bộ chấm chính thức `bird/llm/src/evaluation.py`: chạy SQL dự đoán và SQL vàng trên cùng CSDL, `if set(predicted_res) == set(ground_truth_res): res = 1`; `--meta_time_out` mặc định 30,0 s qua `func_timeout`; `FunctionTimedOut` và mọi ngoại lệ khác → 0 (mất thông tin loại lỗi); `--num_cpus` mặc định 1; tham số `--difficulty` được parse nhưng không dùng — [evaluation.py](https://raw.githubusercontent.com/AlibabaResearch/DAMO-ConvAI/main/bird/llm/src/evaluation.py)
- Định dạng đầu vào: SQL dự đoán và `db_id` nối bởi `'\t----- bird -----\t'`; chạy `sh ./run/run_evaluation.sh` — [repo DAMO-ConvAI/bird](https://github.com/AlibabaResearch/DAMO-ConvAI/tree/main/bird)
- OmniSQL `evaluate_bird.py` (bản trong dự án): `compare_sql` mở transaction, chạy pred rồi gold, `set(predicted_res) == set(ground_truth_res)` → 1, rollback; mọi ngoại lệ → 0; `compare_sql_wrapper` bọc toàn bộ (pred + gold) trong `func_timeout(timeout)`, timeout → 0; `run_eval(..., num_cpus=20, timeout=10)`; kết quả sắp theo `question_id`; vàng lấy trường `SQL` khi tên file chứa "bird" — (đọc cục bộ `d:\Github\text_to_SQL\benchmarks\omnisql\official\train_and_evaluate\evaluate_bird.py`, dòng 27–79, 197–235; repo gốc [RUCKBReasoning/OmniSQL](https://github.com/RUCKBReasoning/OmniSQL))
- Major voting của OmniSQL: chạy mọi SQL mẫu với timeout 10 s, gom theo `frozenset` kết quả, chọn nhóm nhiều phiếu nhất (hòa → mẫu xuất hiện trước theo chỉ số); SQL lỗi bị bỏ, kết quả rỗng vẫn được tính là hợp lệ và có thể thắng phiếu; nếu mọi mẫu lỗi → chọn ngẫu nhiên một mẫu (`random.choice`) — (đọc cục bộ, dòng 160–195)
- OmniSQL: Haoyang Li, Shang Wu, Xiaokang Zhang, Xinmei Huang, Jing Zhang, Fuxin Jiang, Shuai Wang, Tieying Zhang, Jianjun Chen, Rui Shi, Hong Chen, Cuiping Li. "OmniSQL: Synthesizing High-quality Text-to-SQL Data at Scale." arXiv:2503.02240 (đánh giá trên 9 bộ dữ liệu) — [arXiv](https://arxiv.org/abs/2503.02240)
- VES/R-VES nhạy với thời gian: tác giả BIRD tăng timeout lên 3 s/ví dụ, lặp 5 lần, lấy kết quả tốt nhất — [repo DAMO-ConvAI/bird](https://github.com/AlibabaResearch/DAMO-ConvAI/tree/main/bird)

### Inferences
- So sánh tập làm EX "dễ dãi" với ORDER BY (thứ tự sai vẫn đúng) và dòng trùng, nhưng "khắt khe" với cột thừa/thiếu hoặc thứ tự cột khác (tuple khác nhau) — một nguồn false negative mà FLEX ghi nhận (58,13% FN của top-10 do biến thể cấu trúc đầu ra chấp nhận được).
- Vì timeout bao cả SQL vàng, trên CSDL lớn (vd. CSDL nặng) một câu có thể bị chấm 0 dù pred đúng nếu máy chậm; kết quả EX phụ thuộc phần cứng và mức song song (20 tiến trình). Cần báo cáo timeout dùng (theo memory dự án: scorer khớp bài báo ở timeout 60 s — khác mặc định 10 s của code; cần nêu rõ trong KLTN).
- Hàm chọn ngẫu nhiên khi mọi mẫu lỗi làm major voting không hoàn toàn tất định nếu không cố định seed.

### Gaps
- Không lấy được bản `evaluate_bird.py` trực tiếp từ GitHub (404 ở `main/evaluate_bird.py`; file nằm trong thư mục `train_and_evaluate/`); phân tích dựa trên bản cục bộ — chưa đối chiếu commit hash với upstream.
- Bài báo OmniSQL dùng timeout nào khi báo số BIRD dev: không trích xuất được trong phiên này.

## 4. Nhiễu nhãn và các bẫy đánh giá trên BIRD; trần lý thuyết

### Takeaway
Nhiều nghiên cứu độc lập cho thấy nhãn BIRD có nhiễu đáng kể: Wretblad et al. (ACL 2024) thấy 49% câu ở CSDL financial có nhiễu và 20,7% SQL vàng sai; Arcwise ước tính ~32,3% mini-dev lỗi; Jin et al. (2026) báo 52,8% mini-dev và 62,8% Spider 2.0-Snow có lỗi, và sửa nhãn làm thay đổi xếp hạng tới ±9 bậc. FLEX (NAACL 2025) chỉ ra EX có cả false positive và false negative, đề xuất LLM-judge với κ = 87,04 so với chuyên gia.

### Cited Findings
**Wretblad et al. 2024**
- Niklas Wretblad, Fredrik Gordh Riseby, Rahul Biswas, Amin Ahmadi, Oskar Holmström. "Understanding the Effects of Noise in Text-to-SQL: An Examination of the BIRD-Bench Benchmark." Proceedings of ACL 2024 (Volume 2: Short Papers), tr. 356–369. arXiv:2402.12243. Mã/dữ liệu: github.com/niklaswretblad/the-effects-of-noise-in-text-to-SQL — [ACL Anthology 2024.acl-short.34](https://aclanthology.org/2024.acl-short.34); [arXiv](https://arxiv.org/abs/2402.12243v4)
- Tỉ lệ câu có nhiễu: financial 49% (52/106), california_schools 45% (9/20), thrombosis_prediction 40% (8/20), toxicology 35% (7/20), superhero 15% (3/20). SQL vàng sai: financial 20,7% (22/106), california_schools 40% (8/20), thrombosis 30% (6/20), toxicology 10% (2/20), superhero 5% (1/20) — [arXiv HTML v4](https://arxiv.org/html/2402.12243v4)
- 6 loại nhiễu: lỗi chính tả/cú pháp, câu hỏi mơ hồ, SQL sai, đồng nghĩa, viết hoa chuỗi, câu hỏi không ánh xạ được vào CSDL — [arXiv HTML v4](https://arxiv.org/html/2402.12243v4)
- Khi sửa SQL vàng, zero-shot GPT-3.5 vượt DIN-SQL và MAC-SQL (MAC-SQL tụt xuống ngang DIN-SQL); khi sửa cả câu hỏi và SQL, mọi mô hình tăng, zero-shot GPT-4 tốt nhất — [arXiv HTML v4](https://arxiv.org/html/2402.12243v4)

**Arcwise và Jin et al. 2026**
- Arcwise báo cáo 161 ví dụ lỗi trong BIRD Mini-Dev qua kiểm toán thủ công (tỉ lệ 32,3%; một phiên bản khác của bài Jin ghi 36%), được dẫn lại trong — [arXiv 2601.08778](https://arxiv.org/html/2601.08778v2). Không tìm được bài blog gốc của Arcwise.
- Tengjun Jin, Yoojin Choi, Yuxuan Zhu, Daniel Kang. "Pervasive Annotation Errors Break Text-to-SQL Benchmarks and Leaderboards." arXiv:2601.08778 (v1 13/01/2026, v3 19/01/2026); có bản PVLDB Vol. 19, tr. 931 (URL vldb.org/pvldb/vol19/p931-jin.pdf); bản CIDR 2026 tựa "Text-to-SQL Benchmarks are Broken: An In-Depth Analysis of Annotation Errors" — [arXiv](https://arxiv.org/abs/2601.08778); [PVLDB PDF](https://www.vldb.org/pvldb/vol19/p931-jin.pdf); [CIDR 2026](https://vldb.org/cidrdb/2026/text-to-sql-benchmarks-are-broken-an-in-depth-analysis-of-annotation-errors.html); [blog tác giả](https://ddkang.substack.com/p/pervasive-annotation-errors-break)
- Kiểm toán 498 ví dụ Mini-Dev (500, có 2 trùng): 263 lỗi (52,8%). Spider 2.0-Snow: 76/121 ví dụ có gold công khai lỗi (62,8%; một phiên bản báo 66,1%) — [arXiv HTML](https://arxiv.org/html/2601.08778v3)
- Phân loại lỗi (BIRD Mini-Dev / Spider 2.0-Snow, % trên số ví dụ lỗi, có chồng lấn): E1 lệch logic câu hỏi–SQL 29,28% / 48,68%; E2 hiểu sai dữ liệu/lược đồ 57,79% / 57,89%; E3 tri thức miền sai 10,65% / 11,84%; E4 mơ hồ 29,66% / 23,68% — [arXiv HTML](https://arxiv.org/html/2601.08778v3)
- SAR-Agent đạt 83% precision trên Mini-Dev, phát hiện 138/161 lỗi Arcwise (85,7%) và tìm thêm 41,6% ví dụ lỗi so với Arcwise — [arXiv](https://arxiv.org/abs/2601.08778)
- Lấy ngẫu nhiên 100 ví dụ từ BIRD Dev 1.534, sửa 48 ví dụ; đánh giá lại 16 agent mã nguồn mở: thay đổi hiệu năng tương đối −7% đến +31%, thứ hạng −9 đến +9; tương quan hạng với full Dev: tập chưa sửa r_s = 0,85 (p = 3,26e-5), tập đã sửa r_s = 0,32 (p = 0,23) — [arXiv](https://arxiv.org/abs/2601.08778); [arXiv HTML](https://arxiv.org/html/2601.08778v3)

**FLEX (Kim et al., NAACL 2025)**
- Heegyu Kim, Taeyang Jeon, Seunghwan Choi, Seungtaek Choi, Hyunsouk Cho. "FLEX: Expert-level False-Less EXecution Metric for Text-to-SQL Benchmark." Proceedings of NAACL 2025 (Long Papers), tr. 4448–4475. arXiv:2409.19014 (tựa arXiv: "…for Reliable Text-to-SQL Benchmark") — [ACL Anthology 2025.naacl-long.228](https://aclanthology.org/2025.naacl-long.228); [arXiv HTML v4](https://arxiv.org/html/2409.19014v4)
- Trên 200 cặp BIRD được chuyên gia gán nhãn: EX có 21 false positive (không tương đương nhưng EX chấm đúng) và 17 false negative; FLEX (judge GPT-4o) đạt Cohen's κ 87,04 với chuyên gia so với 62,00 của EX — [arXiv HTML v4](https://arxiv.org/html/2409.19014v4)
- Đánh giá lại 50 mô hình công khai trên Spider và BIRD: dịch hạng trung bình ~1,7 (Spider) và 2,2 (BIRD), tối đa 8 và 5; BIRD: SuperSQL lên đầu (FLEX 64,08 vs EX 57,37, +6,71); DAIL_SQL +5,93; với top-10 mô hình BIRD, 54,54% false negative do ground truth sai và 58,13% do biến thể cấu trúc đầu ra chấp nhận được — [arXiv HTML v4](https://arxiv.org/html/2409.19014v4)

**Spider**
- Độ đo Spider cũ (EM) có false negative trung bình 2,5%, tệ nhất 8,1% — [Zhong et al. 2020](https://arxiv.org/abs/2010.02840); sửa ~4% dev vào 06/2020 — [taoyds/spider](https://github.com/taoyds/spider)

### Inferences
- "Trần lý thuyết" của EX trên BIRD dev không phải 100%: nếu ~30–50% ví dụ (mini-dev) có một dạng lỗi nhãn, một phần (không phải tất cả, vì nhiều lỗi vẫn để lại SQL vàng chạy ra kết quả mà mô hình có thể trùng) sẽ chặn trên EX. Ước lượng thô từ Jin et al.: 48/100 ví dụ dev cần sửa; từ Wretblad: 20,7% SQL vàng sai ở financial. Không có nguồn nào công bố một con số trần chính thức.
- Kết quả của Jin et al. (r_s giảm từ 0,85 xuống 0,32) gợi ý: chênh lệch vài điểm EX giữa các phương pháp trên dev_20240627 có thể không phản ánh khác biệt thật; KLTN nên kèm kiểm định thống kê (paired/McNemar) và phân tích lỗi thủ công, và có thể báo thêm kết quả trên dev_20251106.
- Bản dev_20251106 có lẽ là phản hồi chính thức của BIRD trước các phê bình này (thời điểm 11/2025, trước bài Jin 01/2026, sau Wretblad và FLEX) — đây là suy luận về trình tự, không có nguồn xác nhận quan hệ nhân quả.

### Gaps
- Không tìm được bài blog/báo cáo gốc của Arcwise (chỉ có số liệu được dẫn lại); hai con số 32,3% và 36% chưa được hòa giải.
- Không đọc được nội dung PDF PVLDB Vol. 19 (luồng nén), nên số issue/trang cuối/DOI và việc bản PVLDB có khác số liệu arXiv hay không chưa kiểm chứng.
- Wretblad: con số EX cụ thể trước/sau sửa chỉ có trong Hình 2, không có dạng văn bản.
- Thống kê BIRD "error types" của mô hình (phân loại lỗi dự đoán như schema linking, JOIN, evidence…) trong bài BIRD gốc: không trích xuất trong phiên này.
- Bản dev_20251106 sửa bao nhiêu câu so với dev_20240627: chưa công bố; có thể tự diff hai file JSON khi tải về.

## 5. Danh mục tham khảo đầy đủ (dùng cho chương Tài liệu tham khảo)

### Takeaway
Danh sách thư mục chuẩn hóa cho mọi nguồn chính đã dẫn; tên tác giả và venue lấy từ trang arXiv/ACL Anthology/repo chính thức.

### Cited Findings
- [1] J. Li, B. Hui, G. Qu, J. Yang, B. Li, B. Li, B. Wang, B. Qin, R. Cao, R. Geng, N. Huo, X. Zhou, C. Ma, G. Li, K. C. C. Chang, F. Huang, R. Cheng, Y. Li. "Can LLM Already Serve as A Database Interface? A BIg Bench for Large-Scale Database Grounded Text-to-SQLs." NeurIPS 2023 Datasets and Benchmarks Track. arXiv:2305.03111. — [arXiv](https://arxiv.org/abs/2305.03111); trang dự án [bird-bench.github.io](https://bird-bench.github.io/); mã [AlibabaResearch/DAMO-ConvAI/bird](https://github.com/AlibabaResearch/DAMO-ConvAI/tree/main/bird); mini-dev [bird-bench/mini_dev](https://github.com/bird-bench/mini_dev); dev 1106 [HF](https://huggingface.co/datasets/birdsql/bird_sql_dev_20251106)
- [2] T. Yu, R. Zhang, K. Yang, M. Yasunaga, D. Wang, Z. Li, J. Ma, I. Li, Q. Yao, S. Roman, Z. Zhang, D. Radev. "Spider: A Large-Scale Human-Labeled Dataset for Complex and Cross-Domain Semantic Parsing and Text-to-SQL Task." EMNLP 2018. arXiv:1809.08887. — [arXiv](https://arxiv.org/abs/1809.08887); [taoyds/spider](https://github.com/taoyds/spider)
- [3] R. Zhong, T. Yu, D. Klein. "Semantic Evaluation for Text-to-SQL with Distilled Test Suites." EMNLP 2020. arXiv:2010.02840. — [arXiv](https://arxiv.org/abs/2010.02840)
- [4] F. Lei, J. Chen, Y. Ye, R. Cao, D. Shin, H. Su, Z. Suo, H. Gao, W. Hu, P. Yin, V. Zhong, C. Xiong, R. Sun, Q. Liu, S. Wang, T. Yu. "Spider 2.0: Evaluating Language Models on Real-World Enterprise Text-to-SQL Workflows." ICLR 2025 (Oral). arXiv:2411.07763. — [arXiv](https://arxiv.org/abs/2411.07763); [xlang-ai/Spider2](https://github.com/xlang-ai/Spider2)
- [5] G. Lee, H. Hwang, S. Bae, Y. Kwon, W. Shin, S. Yang, M. Seo, J.-Y. Kim, E. Choi. "EHRSQL: A Practical Text-to-SQL Benchmark for Electronic Health Records." NeurIPS 2022 Datasets and Benchmarks Track. arXiv:2301.07695. — [arXiv](https://arxiv.org/abs/2301.07695); [glee4810/EHRSQL](https://github.com/glee4810/EHRSQL)
- [6] N. Wretblad, F. G. Riseby, R. Biswas, A. Ahmadi, O. Holmström. "Understanding the Effects of Noise in Text-to-SQL: An Examination of the BIRD-Bench Benchmark." ACL 2024 (Short Papers), pp. 356–369. arXiv:2402.12243. — [ACL Anthology](https://aclanthology.org/2024.acl-short.34)
- [7] T. Jin, Y. Choi, Y. Zhu, D. Kang. "Pervasive Annotation Errors Break Text-to-SQL Benchmarks and Leaderboards." arXiv:2601.08778, 2026; PVLDB Vol. 19 (p931). — [arXiv](https://arxiv.org/abs/2601.08778); [PVLDB](https://www.vldb.org/pvldb/vol19/p931-jin.pdf) (số issue/DOI chưa xác minh)
- [8] H. Kim, T. Jeon, S. Choi, S. Choi, H. Cho. "FLEX: Expert-level False-Less EXecution Metric for Text-to-SQL Benchmark." NAACL 2025 (Long Papers), pp. 4448–4475. arXiv:2409.19014. — [ACL Anthology](https://aclanthology.org/2025.naacl-long.228)
- [9] H. Li, S. Wu, X. Zhang, X. Huang, J. Zhang, F. Jiang, S. Wang, T. Zhang, J. Chen, R. Shi, H. Chen, C. Li. "OmniSQL: Synthesizing High-quality Text-to-SQL Data at Scale." arXiv:2503.02240, 2025. — [arXiv](https://arxiv.org/abs/2503.02240)

### Inferences
- Nên dẫn BIRD kèm phiên bản dữ liệu và ngày tải (ví dụ: "BIRD dev, bản dev_20240627, tải từ bird-bench.oss-cn-beijing.aliyuncs.com/dev.zip, sha256 cdd6d19f…").

### Gaps
- Venue chính thức (nếu có) của OmniSQL: trang arXiv không nêu; chưa xác minh.
- DOI/số issue PVLDB của Jin et al.: chưa xác minh.
