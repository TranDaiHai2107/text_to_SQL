# MIMIC Text-to-SQL: bộ dữ liệu, baseline và thiết kế đánh giá

Ngày kiểm chứng: **09/10/2026**. Đây là rà soát có nguồn của các nhánh nghiên cứu trực tiếp liên quan; không khẳng định đã bao phủ mọi bài báo từng xuất bản. Ưu tiên paper gốc, repository của tác giả, dữ liệu tải được và scorer kiểm tra được. Số liệu dưới đây là kết quả công bố, không phải kết quả mới của hệ thống này.

## Kết luận để chọn benchmark

**Chạy EHRSQL 2024 trước** để có so sánh chính thức trên MIMIC-IV với dữ liệu tiếng Anh, gold SQL, gold result và scorer. **Dùng CLINSQL 2026 tiếp theo** nếu muốn kiểm chứng trên MIMIC-IV 3.1 với cohort và truy vấn lâm sàng phức tạp. Dùng MIMICSQL như benchmark lịch sử riêng. Chiều SQL → tiếng Anh cần phân biệt mô tả truy vấn với diễn giải kết quả truy vấn.

Không thể chứng minh hệ thống tốt hơn chỉ bằng cách tìm dataset hoặc đổi sang LLM mạnh hơn. Cần cùng dữ liệu, database, split, scorer và ngân sách suy luận; sau đó mới kiểm tra chênh lệch có ý nghĩa.

## 1. Trạng thái repository và vấn đề hiện tại

Remote `https://github.com/TranDaiHai2107/text_to_SQL.git` có HEAD `2f27147c58fb9a80e1dd01d4c69585c2c887fda3`, trùng HEAD local khi kiểm tra bằng `git ls-remote`. Có sửa đổi local có sẵn ở `app.py`, `build_vector_db.py`, `rag_engine.py`; nghiên cứu này không sửa các file đó.

Pipeline hiện có: rewrite hội thoại → retrieval ICD/schema/examples → Groq LLM → SQLGlot validator → PostgreSQL read-only → self-correction → diễn giải kết quả. Benchmark tự xây có 180 câu Việt, 101 examples; collection evaluation bỏ 28 gold SQL trùng, còn 73 examples. Đây là dữ liệu nội bộ, chưa phải benchmark công bố.

Chạy lại **13 unit tests: tất cả pass**. Điều này xác minh các kiểm tra phần mềm hiện có; không chứng minh độ chính xác ngữ nghĩa của LLM. `test_rewrite.py` in expected/actual nhưng chưa tự tính điểm. Không tìm thấy module audio/ASR hay kết quả WER trong các file tracked đã kiểm tra; do đó chưa có bằng chứng repository để xác nhận ASR hoàn tất, dù bạn có thể đã chạy nó bên ngoài repo.

File `evaluate_results.json` ngày 05/10 chỉ ghi **10 câu/mode**, không phải 180. Nó chứa lỗi 429 của **Groq**, model `qwen/qwen3.8-27b`, giới hạn **tokens per day = 200000**. Đây khác Grok của xAI và khác giới hạn context/output mỗi request. `_call_llm()` retry ngắn khoảng vài giây, trong khi log yêu cầu chờ nhiều phút; `evaluate.py` chưa checkpoint từng câu để resume. [Định nghĩa rate limit Groq](https://console.groq.com/docs/rate-limits).

Lỗi mẫu số EX cần xử lý trước khi công bố: `evaluate_one()` để `execution_match=None` khi API/SQL thất bại; `compute_metrics()` bỏ tất cả giá trị None. Kết quả tính lại từ log, giữ lỗi dự đoán trong mẫu số của các câu gold không rỗng:

- `base`: 6/10 = 60%; `icd`: 7/10 = 70%; `schema`: 5/10 = 50%.
- `examples`: 6/10 = 60%, trong khi file ghi 66,7%; có 1 lỗi 429.
- `full`: 1/10 = 10%, trong khi file ghi 100%; có 9 lỗi 429.
- `full_agentic`: 1/10 = 10%, trong khi file ghi 100%; có 9 lỗi 429.

Các tỷ lệ này phản ánh **lần chạy bị gián đoạn**, không phải ước lượng năng lực của model. Cần chạy bù lỗi hạ tầng để hoàn thành benchmark; không tự đổi lỗi quota thành abstention của model, cũng không loại chúng âm thầm khỏi mẫu số.

Các khác biệt scorer khác: bỏ gold rỗng; làm tròn số 6 chữ số; casefold chuỗi; sort giá trị bên trong từng hàng; giới hạn 10.000 hàng evaluation. Sort riêng từng hàng có thể mất liên kết cột; row cap có thể che khác biệt ngoài phần bị cắt. Các lựa chọn này không tương đương scorer chính thức.

## 2. EHRSQL 2024 — lựa chọn thực nghiệm chính

[Paper tổng quan, ClinicalNLP/NAACL 2024](https://aclanthology.org/2024.clinicalnlp-1.62/) và [repository chính thức](https://github.com/glee4810/ehrsql-2024).

Dữ liệu snapshot tải được tại commit `f9e1aa02160d39e3f8df52bf5c69c5cf2e472499`, phiên bản file `*_v1.1.2`:

- Train: **5.124** = 4.674 answerable + 450 unanswerable.
- Validation: **1.163** = 931 answerable + 232 unanswerable.
- Test: **1.167** = **934 answerable + 233 unanswerable**.

Mỗi split có `data.json` (id, question tiếng Anh), `label.json` (id → SQL hoặc chuỗi `"null"`), `answer.json` (id → kết quả truy vấn hoặc `"null"`), `annotated.json`. `tables.json` cung cấp schema. Database SQLite chính thức có **17 bảng**, khác database PostgreSQL 31 bảng của dự án. Nguồn là **MIMIC-IV demo 2.2**, 100 bệnh nhân, có xử lý thời gian và giá trị; thời điểm chuẩn của scorer là **2100-12-31 23:59:00**. [Cấu trúc và preprocessing chính thức](https://github.com/glee4810/ehrsql-2024).

Ví dụ thực từ test, id `bbc6747e134e489a305733da`:

> What was patient 10005348's age on the last hospital stay?

```sql
SELECT admissions.age FROM admissions
WHERE admissions.subject_id = 10005348
AND admissions.dischtime IS NOT NULL
ORDER BY admissions.admittime DESC LIMIT 1
```

Gold result là chuỗi `"[['76']]"`. Đây **không phải** gold câu trả lời tiếng Anh “The patient was 76 years old.”; câu đó có thể là reference do mình bổ sung, nhưng phải ghi rõ nguồn tạo.

Ví dụ unanswerable: câu hỏi về độ trễ cuộc hẹn khoa nephrology, id `5625e6388567182df2aab97b`, có gold `"null"`. Không được coi kết quả truy vấn rỗng là cùng nghĩa với nhãn unanswerable.

**Kiểm chứng offline đã làm:** toàn bộ **934 gold SQL test** được postprocess đúng code tác giả, chạy trên SQLite chế độ chỉ đọc, đối chiếu `answer.json`: **934 thành công, 0 lỗi, 0 timeout, 0 mismatch**. 233 nhãn còn lại có gold answer `"null"`. ID input/SQL/result khớp hoàn toàn. Đây là xác minh dataset, chưa phải benchmark hệ thống của bạn.

### Kết quả chính thức và kiến trúc hệ thống

Theo **Table 3 của overview**, các cặp **RS(0) / RS(10)** trên test:

- LG AI Research & KAIST: **88,17 / 81,32** — self-training, pseudo-label câu unanswerable, ChatGPT và ensemble.
- PromptMind: **82,60 / 74,89** — ensemble GPT-4, ChatGPT, Claude Opus; retrieval examples và đồng thuận để abstain.
- ProbGate: **81,92 / 74,21** — fine-tuned ChatGPT, ngưỡng log-probability và xử lý lỗi.
- KU-DMIS: **72,07 / 59,21** — question templatization, fine-tuning và consistency.
- AIRI NLP: **68,89 / 44,04** — T5-3B, logistic regression, kiểm tra thực thi.
- LTRC-IIITH: **66,84 / 43,70** — SQLCoder-7b-2 và abstention.
- Saama Technologies: **53,21 / 36,08** — cây quyết định, CodeLlama-7b, ChatGPT.
- TEAM_optimist: **14,14 / −713,37** — SQLCoder-7b-2, in-context learning.
- Abstain-all: **20,00 / 20,00**.

[Nguồn điểm và mô tả, Table 3](https://aclanthology.org/2024.clinicalnlp-1.62.pdf). Không gọi RS(0)=88,17 là EX=88,17: RS(0) còn thưởng từ chối đúng câu unanswerable.

### Cách chấm chính thức

Với mức phạt c: đúng kết quả answerable +1; từ chối đúng unanswerable +1; từ chối câu answerable 0; trả lời sai hoặc trả lời câu unanswerable −c. **RS(c)=100×(số đúng − c×số trả lời sai)/N**. Điểm có thể âm. EX riêng trên 934 answerable là metric bổ sung, cần ghi mẫu số rõ.

Scorer tác giả postprocess SQL thời gian, làm tròn giá trị số 3 chữ số, chuyển sang chuỗi, sort hàng rồi chỉ giữ tối đa 100 hàng để so sánh. Nếu muốn đánh giá nghiêm ngặt hơn, báo riêng; vẫn giữ scorer gốc cho bảng so sánh chính thức. `scoring_v2.py` dùng kết quả đã truy hồi là metric experimental, không phải gold văn xuôi.

Để tái lập paper 2024, nên xác minh lịch sử commit/dataset version đúng lần thi. Snapshot hiện tại kiểm chứng được, nhưng chưa xác nhận mọi nhãn giống hệt bản dùng để chấm leaderboard năm 2024. Repository EHRSQL gốc còn thông báo sửa annotation v1.5.0 năm 2026; vì vậy luôn pin commit, không dùng tên dataset chung chung. [EHRSQL gốc](https://github.com/glee4810/EHRSQL).

## 3. CLINSQL — MIMIC-IV 3.1, EACL 2026

[Paper Patient-Similarity Cohort Reasoning in Clinical Text-to-SQL](https://aclanthology.org/2026.eacl-long.64/), [code/data](https://github.com/Barryshen1/ClinSQL), [dataset tác giả](https://huggingface.co/datasets/yifeis02/ClinSQL).

**633 bài expert-annotated**, snapshot có **190 validation + 443 test**; sáu nhóm lâm sàng, ba độ khó, gold BigQuery SQL, reference CSV, rubric SQL và rubric result. Không có train split như EHRSQL. Full MIMIC-IV 3.1 trên BigQuery cần quyền PhysioNet; subset 500 bệnh nhân của bạn không cho phép đối chiếu trực tiếp reference CSV.

Table 4, CoT + tối đa hai self-refinement, **Avg. Test Execution Score**: GPT-5-mini **74,67**; Gemini-2.5-Pro **73,73**; DeepSeek-R1 **69,15**; GPT-5 **68,42**; GPT-4.1 **67,79**; Gemini-2.5-Flash **65,01**; DeepSeek-V3.1 **60,71**; Grok-4-Fast-Reasoning **58,46**; Qwen3-Coder-480B-A35B-Instruct **58,18**. [Table 4](https://aclanthology.org/2026.eacl-long.64.pdf).

**Execution Score này là điểm rubric có GPT-5 judge, không phải strict EX so hai result sets.** Tái lập phải giữ prompt, self-refinement budget, database, rubric và judge. Dữ liệu/gold đã tải; chưa chạy gold trên BigQuery và chưa gọi judge. Paper có lệch số DeepSeek-R1 giữa abstract/phần diễn giải; dùng giá trị Table 4 là 69,15.

## 4. MIMICSQL và các hệ thống trên MIMIC-III

### TREQS, WWW 2020

[Paper Wang, Shi, Reddy](https://people.cs.vt.edu/~reddy/papers/WWW20.pdf), [repository/dataset](https://github.com/wangpinggl/TREQS).

Dataset 10.000 cặp, mỗi variant **8.000 train / 1.000 dev / 1.000 test**. Schema gom thành năm bảng `DEMOGRAPHIC`, `DIAGNOSES`, `PROCEDURES`, `PRESCRIPTIONS`, `LAB`; questions dựa vào 100 admissions sampled. TREQS dùng Seq2Seq, attentive copying và recovery giá trị theo lookup.

Table 2, **natural-language test bản gốc**: TREQS **LF 48,6%, EX 55,6%**; +recover **LF 55,6%, EX 65,4%**. **Template test** +recover: LF **91,2%, EX 94,0%**. Không lấy 94% để so câu tự nhiên. Bản `mimicsql_natural_v2` có điểm test +recover **LF 54,7%, EX 69,0%**, theo README tác giả.

Các file là JSON Lines dù đuôi `.json`; fields `key`, `question_refine`, `sql`, logical `format`. Cả ba variants đã tải. Tuy nhiên file `evaluation/mimic_db/mimic.db` trong snapshot **0 byte**: có Q/SQL chuẩn nhưng chưa có database thực thi usable. Cần dựng đúng preprocessing từ MIMIC-III theo tác giả; không dùng MIMIC-IV của bạn thay thế.

### MedTS, JMIR Medical Informatics 2021

BERT encoder + grammar-based decoder sinh AST SQL; test MIMICSQL **LF 78,4%, EX 89,9%**. Biến thể BioBERT: LF **79,0%, EX 90,4%**. Đây là baseline mạnh hơn TREQS trên benchmark đó. [Paper gốc, Tables 2 và 4](https://medinform.jmir.org/2021/12/e32698/).

### MIMICSQL*, MIMIC-SPARQL*, UniQA

Park et al., MLHC 2021 tạo đối chiếu schema đơn giản/original và SQL/SPARQL. [Dataset và code](https://github.com/junwoopark92/mimic-sparql). Dấu `*` là biến thể riêng; SPARQL là truy vấn graph, không phải SQL.

Bae et al., Unified Encoder-Decoder/UniQA: trên **MIMICSQL*** sau recovery, LF **88,2±1,2%**, EX **93,4±0,8%**, structural accuracy **90,5±1,3%**, mean/std qua 5 seeds. [Paper, Table 1](https://arxiv.org/pdf/2111.14703). Không gộp với MIMICSQL năm bảng gốc.

### Generalization/MIMICSQL 2.0, Tarbell et al. 2023

T5 trên paraphrased split gốc đạt **LF 89,9%, EX 93,6%**. Trên split mới, T5 **LF 13,0%, EX 50,3%** với paraphrase→paraphrase; template→template **LF 14,9%, EX 27,8%**. T5 + back-translation đạt EX **51,9%** ở paraphrase→paraphrase. [Paper, Tables 3–4](https://arxiv.org/pdf/2303.12898).

Điều này cho thấy nhớ cấu trúc tương tự trong train/test có thể làm điểm cao nhưng tổng quát hóa yếu. Repo tác giả `AnthonyMRios/mimic-sql-data` hiện **rỗng khi clone**; chưa lấy được split chính thức mới. Không tự tái chia rồi gọi đó là MIMICSQL 2.0 chuẩn.

### MedT5SQL, Frontiers 2024

Fine-tune T5-base trên `mimicsql_natural_v2`: **exact string/LF 80,63%**, approximate string matching **98,937%**; manual **90% trên 20 câu**. Không có EX tương ứng được kiểm chứng ở đây, và manual 18/20 không phải accuracy cả dataset. [Paper, Table 7](https://www.frontiersin.org/journals/big-data/articles/10.3389/fdata.2024.1371680/full). Paper có chỗ viết 80,1%; ưu tiên bảng 80,63% và ghi sự khác biệt.

### EHRSQL gốc, NeurIPS 2022

Câu hỏi từ 222 nhân viên bệnh viện, MIMIC-III/eICU, có unanswerable và biểu thức thời gian. T5 + percentile abstention trên **MIMIC-III test**: execution precision **88,8%**, execution recall **91,1%**, **F1_exe 89,9%**. Đây không phải EX=89,9%. [Paper, Table 5](https://arxiv.org/html/2301.07695v6). Khác EHRSQL 2024 MIMIC-IV; snapshot repo đã đổi annotation cần pin bản.

### EHRAgent, 2024

GPT-4-0613 + code interface, kiến thức miền, retrieval ví dụ và feedback sửa code; dùng bốn demonstrations, tối đa 10 bước. Table 1: **success rate 58,97% trên MIMIC-III**, **53,10% eICU**, **69,70% TREQS**; completion rate tương ứng 85,86%, 91,72%, 88,02%. [Paper](https://www.cs.emory.edu/~jyang71/files/ehragent.pdf). Agent có thể dùng Python; SR/CR không được trộn với LF, EX hoặc RS.

### Graph-empowered Text-to-SQL, Pattern Recognition 2026

LLM + graph structure injection; tác giả công bố **EX 94,2% trên MIMICSQL**. [Trang paper gốc/abstract](https://www.sciencedirect.com/science/article/pii/S0031320325004601). Chưa có full protocol/code được xác minh trong rà soát này; dùng làm kết quả công bố tham khảo, chưa làm đối chứng tái lập.

### CBR-to-SQL, preprint v2 tháng 4/2026

RAG tách retrieval cấu trúc câu hỏi và ánh xạ entity, dùng GPT-4o; rất gần hướng hệ thống của bạn. Table 1: MIMICSQL **EX 89,4%, LF 86,2%**, baseline RAG **86,0% / 82,5%**; EHRSQL **89,5% / 72,9%**, baseline **81,8% / 67,6%**. [Paper v2](https://arxiv.org/html/2603.05569v2).

**Hai vấn đề nguồn:** đoạn prose đảo 89,9/89,4 giữa CBR và MedTS so với Table 1; bảng EHRSQL gọi điểm các đội EX nhưng số khớp RS(0) của shared task, vốn còn tính từ chối đúng. Không suy ra CBR vượt leaderboard chính thức từ bảng này. Cần chạy code của họ cùng scorer; code được paper dẫn ở [anonymous repository](https://anonymous.4open.science/r/CBR-to-SQL-9172/), chưa tái lập ở đây.

### Nhánh bổ sung mới

[Robust Clinical Querying with Local LLMs, 2025 — repository tác giả](https://github.com/fipu-lab/med-rag) báo MIMICSQL NL2SQL tốt nhất GPT-4o **66,1% EX**, GPT-5 **64,6%**, 27.000 generations = 9 models × 3 runs × 1.000 câu. Paper MDPI không truy cập full text được trong phiên này, nên không xếp số này vào bảng đối chứng đã kiểm chứng protocol. Đây là lý do không khẳng định model mới hơn luôn tốt hơn trên mọi thiết lập.

## 5. SQL → tiếng Anh: hai loại output

### SQL → mô tả ý nghĩa truy vấn

Input là SQL + schema; output là câu hỏi/mô tả thao tác, không có giá trị đáp án thực tế. Có thể đảo Q/SQL của MIMICSQL/EHRSQL để tạo **protocol mới**, nhưng chưa phải benchmark reverse chính thức trên MIMIC với baseline sẵn.

Nguồn phù hợp có sẵn: **Semantic Captioning, COLING 2025**, [paper](https://aclanthology.org/2025.coling-main.536/) và [code/data](https://github.com/aliwister/ast-icl). Đã tải ba test sets: Spider-S2T **274**, CoSQL-S2T **290**, SParC-S2T **289**; từng mẫu có `query`, nhiều `utterances`, `idx`.

Table 1, **Mistral-7B, AST-ICL-TOP-2, Spider-S2T**: BLEU **0,4348**, BERTScore-1 **0,8920**, BERTScore-2 **0,8649**, AlignScore **0,8645**. Mistral zero-shot BLEU **0,2226**, random-2 **0,4138**. Không đổi 0,4348 thành “accuracy 43,48%”. Đây là benchmark ngoài miền y tế.

### Kết quả SQL → câu trả lời

Đây là tác vụ gần `interpret_result(question, sql, df)` nhất. Cần Q + SQL + result table + gold prose hoặc gold facts. EHRSQL 2024 đã có gold result nhưng **không có reference văn xuôi tiếng Anh chuẩn** cho tác vụ này.

[QR2T của DARE Lab](https://darelab.athenarc.gr/systems/qr2t/) nghiên cứu verbalization query results bằng T5/table-to-text và có benchmark; khác SQL captioning, không phải MIMIC. Chưa kiểm chứng được bộ tải và kết quả đủ chi tiết trong phiên này để đưa thành baseline trực tiếp.

Khuyến nghị phase hiện tại: dùng gold SQL thực thi lấy gold result để đánh giá riêng answer generation; chấm giá trị số, đơn vị, thực thể, phủ định, tập hợp và claims không được hỗ trợ. Nếu tạo reference English bằng template/chuyên gia, ghi đây là annotation mới; nếu chỉ đảo SQL→question, ghi tác vụ mô tả truy vấn. Không cấp câu hỏi gốc làm input nếu mục tiêu là đánh giá SQL-only captioning, vì model có thể chỉ paraphrase nó.

Đánh giá end-to-end thêm một lượt với SQL do hệ thống sinh; tách lỗi sinh SQL và lỗi diễn giải. LLM judge chỉ làm metric phụ với rubric/version/các mẫu kiểm tra của người; không dùng duy nhất judge để tuyên bố chính xác lâm sàng.

## 6. SCARE cho self-correction và câu hỏi mơ hồ

[Paper SCARE 2025](https://arxiv.org/html/2511.17559v1), [code/data](https://github.com/glee4810/SCARE). **4.200 triples** = 1.400 MIMIC-III + 1.400 MIMIC-IV + 1.400 eICU, gồm Q + candidate SQL + expected output. Đã xác minh ba file **`correction-data/*_test_set_correction_data.json`** có đúng 1.400 mẫu/file. `data_final` chứa câu nguồn, không phải toàn bộ triples.

Table 3: Single-Turn-Veri correction rate **52,1%**, coverage **98,1%** cho answerable-incorrect; Single-Turn-Cls ambiguous F1 **54,0%**, unanswerable F1 **80,6%**. Đây là correction/classification metrics, không phải EX của pipeline sinh SQL. Dataset hợp với `generate_sql_with_correction()`, nhưng database riêng tải ngoài; chưa thực thi gold SCARE ở đây.

## 7. WER, EX và việc chọn metric

**WER=(S+D+I)/N_ref** đo sai khác từ trong transcript ASR, càng thấp càng tốt. Khi phase này chỉ nhận text tiếng Anh, WER không phải metric chính. SQL đổi alias/thứ tự điều kiện vẫn đúng, còn một chữ NOT sai có thể đảo nghĩa toàn bộ; khoảng cách từ không phản ánh đúng độ chính xác SQL.

Các paper được kiểm chứng ở trên dùng EX/LF/structural, F1 execution, RS, rubric score hoặc BLEU/BERTScore/AlignScore; không có điểm WER chuẩn tương ứng để bạn đối chiếu. Nếu muốn đo WER ASR ở phase khác, cần audio + transcript gold + chuẩn tokenize, tách khỏi benchmark NL→SQL.

Metric nên báo:

- EHRSQL 2024: **RS(0), RS(10), EX trên answerable**, tỷ lệ abstention, wrong-answer rate, latency, tokens/cost, API failures và completion coverage.
- MIMICSQL: **EX và LF**, ghi variant natural/template/v2, cùng database/preprocessing.
- CLINSQL: **SQL Score và Execution Score rubric**; strict EX thêm phải mang tên riêng.
- SQL captioning: metric NLG đúng code paper + kiểm tra ngữ nghĩa.
- Result verbalization: **factual accuracy/coverage/hallucination** với facts lấy từ gold result; NLG score phụ nếu có reference prose.

## 8. LLM nên thử và chi phí hiện hành

Đây là **shortlist để chạy pilot**, không khẳng định đã chứng minh tốt hơn Qwen hiện tại trên MIMIC. Context lớn không giải quyết quota miễn phí theo ngày; cả API trả phí cũng có RPM/TPM/tier limits.

Theo [OpenAI model catalog kiểm tra 09/10/2026](https://developers.openai.com/api/docs/models):

- **GPT-6.1 Sol (`gpt-6.1-sol`)**: lựa chọn cân bằng để thử làm main model, context 1,05M, giá **$2 input / $10 output mỗi 1M tokens**.
- **GPT-6 Luna (`gpt-6-luna`)**: đối chứng tiết kiệm, **$0,10 / $0,50**, cùng context 1,05M.
- **GPT-6 Astra (`gpt-6-astra`)**: đối chứng chất lượng cao, **$10 / $50**, cùng context; tốn kém hơn, chỉ nên cân nhắc sau pilot.

Theo [Claude official model overview](https://platform.claude.com/docs/en/models/overview): **Sonnet 5.5 (`claude-sonnet-5-5`)**, context 1M, **$2 / $10**, là đối chứng khác nhà cung cấp; **Opus 5.5** **$4 / $20** nếu ngân sách cao hơn. Không có điểm MIMIC chính thức được tìm thấy cho những model hiện hành này trong rà soát.

Theo [Gemini models](https://ai.google.dev/gemini-api/docs/models): **Gemini 3.8 Flash (`gemini-3.8-flash`)** cho đối chứng Flash hiện hành. [Pricing standard](https://ai.google.dev/gemini-api/docs/pricing) hiển thị **$1,50 / $9**, batch **$0,75 / $4,50**. Chọn paid tier đủ throughput; không giả định free tier đủ cả benchmark.

**Baseline theo paper:** GPT-5-mini có bằng chứng CLINSQL 74,67 nhưng [trang API hiện đánh dấu Deprecated](https://developers.openai.com/api/docs/models/gpt-5-mini); cần kiểm tra quyền gọi/snapshot nếu tái lập, không chọn làm mặc định mới. DeepSeek-R1 có bằng chứng CLINSQL 69,15; cần host/API phù hợp. Các model lớn này không chạy đầy đủ trên GPU laptop 4GB của dự án. SQLCoder/MedGemma có tên chuyên biệt không đảm bảo tốt hơn: CLINSQL Table 4 cho điểm thấp trong setup đó.

**Đề xuất thực dụng:** pilot GPT-6.1 Sol + GPT-6 Luna + Claude Sonnet 5.5 trên 50–100 câu validation phân tầng, giữ prompt/RAG giống nhau; thêm Gemini 3.8 Flash nếu muốn so nhà cung cấp. Chọn model theo **EX/RS, tỷ lệ hoàn thành, chi phí và latency đo được**, rồi khóa model/version cho full test. Không chọn bằng điểm test.

Ví dụ ngân sách giả định một mode EHRSQL test, mỗi câu 6.000 input + 600 output, một call/câu: **7,002M input + 0,7002M output**. GPT-6.1 Sol khoảng **$21,006**, Luna **$1,0503**, Sonnet 5.5 **$21,006**, Astra **$105,03**, Gemini 3.8 Flash **$16,805**. Đây chỉ là phép tính từ đơn giá; chưa tính thinking tokens, retry, correction, rewrite, judge, cache, thuế. Sáu modes nhân khoảng sáu trước correction. Theo quota log 200k/ngày, input scenario đã tương đương khoảng 35 ngày nếu hạn mức vẫn vậy; lịch reset thực phụ thuộc nhà cung cấp.

## 9. Thiết kế thực nghiệm để chứng minh cải thiện

1. **Cố định benchmark**: EHRSQL 2024 snapshot này để triển khai; đối chiếu lịch sử bản thi trước khi ghi “vượt điểm chính thức 2024”. Database SQLite đi kèm, 17 bảng, clock chuẩn, đúng scorer; gold không vào prompt.
2. **English-only middle phase**: câu English vào retrieval/prompt; descriptions/examples từ train English. Không dịch test sang Việt rồi đo như English benchmark. Validator và database adapter phải đọc schema benchmark, không hardcode 31 bảng/PostgreSQL. EHRSQL có `cost`, `admissions.age`, hàm SQLite; không thay bằng cột/bảng gần giống.
3. **Đối chứng công bằng**: cùng LLM/prompt budget/database, so `base`, ICD/entity retrieval, schema retrieval, example retrieval, full, full+self-correction. Tất cả mode hiện đều đi qua validator; “base không RAG” không có nghĩa “base không validation”. Giữ correction budget và first-pass/final scores rõ.
4. **Train-only retrieval**, threshold chọn trên validation; khóa cấu hình trước test. Loại exact SQL overlap chưa đủ tránh template/paraphrase leakage. Hiện loader của dự án dùng gold test để chọn bệnh nhân bao phủ ICD; không dùng cách sampling phụ thuộc test này để dựng benchmark chính thức.
5. **Checkpoint từng câu**, id/split/model/prompt hash/config, SQL từng attempt, lỗi, tokens, latency. Lỗi 429 tạm dừng/resume theo retry-after và quota; không gọi lại toàn bộ tập đã hoàn thành, không retry vô hạn, không gộp lỗi mạng với lỗi SQL ngữ nghĩa.
6. **Báo mẫu số và độ phủ**, câu unanswerable, câu gold rỗng theo scorer gốc. Tách kết quả SQL và kết quả diễn giải. Không sử dụng custom EX thay RS để claim vượt đội thi.
7. **Thống kê paired**: mỗi hệ thống cùng ID câu hỏi; EX báo bootstrap confidence interval và McNemar khi thích hợp. RS báo bootstrap chênh lệch per-question. Nhiều lần chạy có seed/version cố định; nếu dùng temperature=0 vẫn ghi số lần chạy. Không chọn seed thuận lợi.
8. **Kiểm tra đóng góp**: đổi model mạnh + kiến trúc mới có thể làm điểm cao do model. Để chứng minh RAG/agentic có tác dụng, ablate trên cùng model; nếu vượt baseline lịch sử, diễn đạt rõ cả hai khác biệt.
9. **CLINSQL riêng**: giữ BigQuery/full MIMIC-IV 3.1, judge/rubric và self-refinement của paper. Nếu port PostgreSQL/subset, gọi đó là adapted protocol; chạy lại baseline trên cùng bản port, không so trực tiếp reference paper.
10. **Phần diễn giải English**: benchmark Semantic Captioning để đo SQL comprehension ngoài miền; trên MIMIC bổ sung gold facts/reference theo protocol công khai. Chưa đủ nguồn để tuyên bố có sẵn một benchmark MIMIC hai chiều với gold prose và WER chuẩn.

## 10. Các tài nguyên đã bàn giao

- `research/sources/ehrsql-2024/`: repo/scorer/schema/SQLite/input/gold/result chính thức đã tải.
- `research/datasets/ehrsql-2024/{train,valid,test}.inputs.jsonl`: chỉ id + question, giữ text/ID gốc.
- `research/datasets/ehrsql-2024/{train,valid,test}.gold.jsonl`: gold SQL/result tách riêng tránh lọt vào input.
- `research/sources/TREQS/mimicsql_data/`: cả ba variants; database đi kèm rỗng, chưa sẵn sàng EX.
- `research/sources/ClinSQL/data/`: benchmark, validation/test, SQL/result/rubric; chưa chạy BigQuery/judge.
- `research/sources/ast-icl/s2t-datasets/`: ba datasets reverse SQL2Text có multi-reference.
- `research/sources/SCARE/correction-data/`: đúng 4.200 triples; database tải ngoài, chưa chạy scorer.
- `research/benchmark_manifest.json`: commit, SHA256, số lượng, preflight và audit local EX.
- `research/audit_benchmarks.py`: tái chạy audit offline, không gọi LLM.

Repository upstream giữ nguyên trong `sources/` và được ignore khỏi Git dự án để tránh commit nested repos, database và inference outputs lớn. File manifest giữ dấu vết phiên bản. Không tải dữ liệu MIMIC-IV full credentialed; không phát sinh cuộc gọi LLM trả phí, không push remote, không triển khai thay model trong ứng dụng.

Lệnh audit:

```powershell
.\.venv\Scripts\python.exe research\audit_benchmarks.py
```

Ưu tiên tiếp theo là adapter EHRSQL English/SQLite + scorer chính thức + sửa mẫu số/checkpoint; sau khi pilot chọn model mới chạy full benchmark. Chỉ khi có lần chạy hoàn chỉnh cùng protocol mới có cơ sở kết luận hệ thống chính xác hơn.
