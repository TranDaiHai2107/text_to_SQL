# Nghiên cứu EHRSQL 2024 cho V6 không fine-tune — 07/11/2026

Đã đối chiếu phương pháp, kết quả, ablation, giới hạn và các phụ lục liên quan của đủ8 paper đội thi và bài overview. Đã tải9 PDF từ ACL (89trang cả references/phụ lục), lưu text từng trang và SHA-256 tại `research/sources/ehrsql2024_papers/manifest.json`. Không lấy abstract làm toàn bộ phương pháp; không tuyên bố đã chạy hoặc tái hiện code của cả8 đội.

Ràng buộc hiện tại: không fine-tune, kể cả LoRA/QLoRA/self-training, không train classifier khác. Embedding/model có sẵn được dùng inference không đổi trọng số. V6 và kết quả74,9786 giữ nguyên; lượt này chỉ nghiên cứu, không đọc lỗi test mới, không gọi model/API, không sửa pipeline.

## Công nghệ của đủ8 đội

- **LG AI Research & KAIST / PLUQ — RS10 81.32.** GPT-3.5-Turbo-0125. Công nghệ: seed fine-tuning; unlabeled dev/test null pseudo-labeling; second fine-tuning; max token entropy; execution filtering. Không áp dụng PLUQ nguyên bản khi cấm fine-tune; chỉ mượn hướng dẫn answerability và filtering. [Paper](https://aclanthology.org/2024.clinicalnlp-1.61/); nguồn chi tiết: Sections3–4;Table1,3,4.

- **PromptMind — RS10 74.89.** GPT-4, Claude-3 Opus, FT GPT-3.5. Công nghệ: AnglE + PubMedBERT; z-normalization retrieval fusion; column sample values; execution unanimity across models; RAFT branch. Nhánh GPT-4+Opus không fine-tune RS10=65.72; không gán74.89 cho no-FT. [Paper](https://aclanthology.org/2024.clinicalnlp-1.34/); nguồn chi tiết: Sections4–6;Table2–4.

- **ProbGate — RS10 74.21.** FT GPT-3.5-turbo-0125. Công nghệ: bottom10 non-reserved token logprobs; rank-based abstention; GEF. Lọc logprob cần provider trả dữ liệu thật và calibration mới; cache V6 không có logits để phục dựng. [Paper](https://aclanthology.org/2024.clinicalnlp-1.65/); nguồn chi tiết: Section3.3–3.5;Algorithm1;Table1–2.

- **KU-DMIS — RS10 59.21.** FT GPT-3.5 + GPT-4-turbo. Công nghệ: masked-neighbor retrieval; question templatization; two-step schema detail/self-reflection; value-based table-column verification; intent check + voting. Rewrite và intent verification có thể chuyển sang prompting; giữ nguyên ràng buộc câu gốc. [Paper](https://aclanthology.org/2024.clinicalnlp-1.64/); nguồn chi tiết: Section3;Table3,5;Appendices.

- **AIRI NLP — RS10 44.04.** FT T5-3B + logistic regression; GPT ICL/debugger experiments. Công nghệ: schema overlap and wording features; query correspondence classifier; SQL result inspector; 5-shot SentenceBERT retrieval; DIN-SQL debugger experiment. Không train classifier; debugger của paper làm điểm giảm, không sao chép lọc mọi aggregate0. [Paper](https://aclanthology.org/2024.clinicalnlp-1.43/); nguồn chi tiết: Sections3–5;Table1.

- **LTRC-IIITH — RS10 43.70.** SQLCoder-7b-2. Công nghệ: separate abstention and SQL models; schema comments PK/FK; confidence threshold; execution errors; vLLM serving. QLoRA vẫn là fine-tune; lấy ý tưởng schema rõ nghĩa và guard, không copy threshold-0.4. [Paper](https://aclanthology.org/2024.clinicalnlp-1.66/); nguồn chi tiết: Sections4–6;Table1.

- **Saama / SCAS — RS10 36.08.** LoRA CodeLlama-7b-Instruct + Azure GPT-3.5 selector. Công nghệ: TF-IDF NB/SGD/CatBoost ensemble; LoRA answerability classifier; ICL selector; LoRA SQL generation; retrieved few-shot via MPNet. Không train bất kỳ classifier; selector API thử được nhưng early rejection có false negatives. Paper ghi36.07, overview36.08. [Paper](https://aclanthology.org/2024.clinicalnlp-1.63/); nguồn chi tiết: Sections3–5;Table1;AppendicesA–E.

- **TEAM_optimist / Project PRIMUS — RS10 -713.37.** SQLCoder / sqlcoders. Công nghệ: schema-in-prompt; task instructions; SQL-or-null output. Paper nêu fine-tune tổng quát nhưng không pin quy trình EHR FT; overview đánh dấu không FT. Không ưu tiên đổi model. [Paper](https://aclanthology.org/2024.clinicalnlp-1.41/); nguồn chi tiết: Section3–5;Table1.

## Điểm cần sửa khi diễn giải nguồn

- Overview Table3 đánh dấu PLUQ không fine-tune, nhưng paper PLUQ mô tả rõ hai lượt fine-tune. Dùng mô tả phương pháp chi tiết;81,32 không phải mốc no-FT.
- PromptMind65,72 là cấu hình hai model không FT;74,89 có FT. Không cộng các mức cải thiện của các paper hoặc dùng chúng làm dự báo V6.
- Saama53,21 là RS0, không phải RS10. Điểm RS10 final overview36,08; paper team36,07, giữ riêng khác biệt báo cáo.
- PRIMUS là paper liên kết với TEAM_optimist trong overview. Lời bàn chung về training của pretrained model không chứng minh đã EHR-fine-tune; recipe/checkpoint thiếu.
- Các thí nghiệm dev/train/custom split hoặc pseudo-labeling test không nhãn phải phân biệt với một lần suy luận trên test chưa dùng thích nghi.

## Đối chiếu với code V6 hiện tại

Đã có:3 nguồn RAG; dense MiniLM+BM25 và masked-question/AST reranking; full17-table schema; dictionary/value grounding;3 route cùng DeepSeek; plan route thinking; bounded execution repair; guard; fingerprint fullrows/numeric3; strict3 selection; compiler metadata/AST; renderer/scorer English.

Do đó, RAG, execution voting, schema, dictionary, thinking và kiểm tra syntax không phải thành phần mới cần thêm lần nữa. Chưa có multi-embedding lâm sàng riêng, canonical-question LLM branch có kiểm tra bảo toàn nghĩa, hoặc verifier ngữ nghĩa độc lập. Ba route cùng model không tương đương ensemble ba model khác nhau của PromptMind.

## Các hướng nên thử, theo thứ tự

**1. Kiểm tra question–SQL contract có bằng chứng, giữ nguồn bất biến.** Dựa ý tưởng verification của KU-DMIS, mở rộng cách phân tích câu hỏi thành slots: đối tượng, đại lượng, aggregate, điều kiện, khoảng thời gian, visit scope, đơn vị, output columns. So với SQL AST; nếu bất đồng thì chỉ từ chối hoặc tạo proposal riêng khi có evidence. Ví dụ COUNT thay AVG, first admission thay current admission hoặc bỏ điều kiện thời gian. Rule AST đã có phải được tái sử dụng, không viết lại dưới tên mới. Phần hard constraints rõ có thể chạy offline; giải nghĩa mới bằng LLM sẽ thêm call. Không cho reviewer tự xoá điều kiện để query chạy được.

**2. Retrieval ngữ nghĩa lâm sàng riêng.** Theo PromptMind, thử thêm pretrained clinical encoder, kết hợp với dense hiện tại+BM25+masked skeleton; không fine-tune encoder. Chuẩn hoá/fusion rank, chọn theo dev; không trộn trực tiếp cosine khác model hay coi PubMedBERT raw mặc nhiên là sentence embedder tốt. Tách tác động clinicalretrieval khỏi việc chỉ tăng few-shot/token. Nguồn dictionary metadata và bệnh nhân được giữ phân biệt.

**3. Nhánh canonical-question có guard.** Theo KU-DMIS, lấy template từ train, viết lại câu hỏi rồi sinh một candidate riêng. Bảo toàn patientID, giá trị/số, phủ định, điều kiện, first/last/current, time interval/calendar và đại lượng. Nếu guard không chứng minh tương đương thì bỏ rewrite, giữ nguyên câu gốc. Không thay mọi câu bằng template gần nhất hoặc ép câu unanswerable thành answerable. Nhánh này khác rewrite hội thoại tiếng Việt của ứng dụng.

**4. Verifier/ensemble API độc lập có ngân sách.** Theo PromptMind và CAS, thử một pretrained verifier/model khác cho câu rủi ro hoặc disagreement; yêu cầu đối chiếu cụ thể từng claim câu hỏi với biểu thức SQL. Ban đầu verifier chỉ approve/abstain, không sửa SQL tự do. Trường hợp cả3route cùng sai vẫn có thể qua voting; thay đổi prompt của cùng model không bảo đảm độc lập. Cần ablation cùng ngân sách hoặc báo đầy đủ sốcall/tokens/cost; không tự chuyển model tài khoản.

**5. Confidence filtering nếu API thực sự cung cấp token logprobs.** ProbGate/LTRC/PLUQ cần dữ liệu xác suất thật. V6 cache generation đang không lưu logprobs; không suy diễn logits/entropy từ văn bản hoặc biến consensus thành xác suất. Top-k logprobs không tự là entropy đầy đủ vocabulary; phải nêu định nghĩa ước lượng. Không copy425,-0.4 hoặc7% từ paper. Nếu không có API support, bỏ arm này.

Các hướng trên là đề xuất kỹ thuật từ nghiên cứu, chưa có điểm V6 chứng minh tăng. Không dùng classifier kiểu length/first-word làm hardgate; không lọc mọi COUNT=0 vì0 có thể là đáp án đúng; không thêm vòng self-correction không giới hạn. AIRI và Saama cung cấp bằng chứng thực nghiệm trực tiếp cho các rủi ro này.

## Thiết kế thí nghiệm tiếp theo chỉ trên dataset paper

- Giữ V6 làm control, không đổi metric/scorer/database/split; không cần tải thêm dataset.
- Dùng train làm nguồn ví dụ, dev làm phát triển/soablation với self-exclusion; dev hiện đã tiếp xúc nên không gọi là holdout độc lập.
- So từng thành phần trước, rồi mới thử kết hợp: contract verifier; clinicalretrieval; guardedrewrite; independentverifier. Không cộng dồn số điểm paper để dự báo.
- Báo RS10 chính, EX, wrong, false abstention, coverage, precision, tokens/cost. Với lựa chọn không giữ LLM training, train chỉ làm retrieval/metadata evidence.
- Khóa policy/prompt/code trước một lần test đủ1.167câu. Không điều chỉnh theo lỗi test; test cũ có exposure lịch sử phải công bố.
- English→SQL→English tiếp tục dùng predictionSQL thật; renderer theo mẫu và metric tự xây báo riêng, không gán cho các paper điểm English họ không công bố.

**Ưu tiên triển khai:** contract verification rõ nghĩa → clinicalretrieval → guardedrewrite; model diversity chỉ sau khi dev cho bằng chứng và ngân sách phù hợp. Chưa có cơ sở cam kết vượt81,32 hoặc thêm công nghệ là tự tăng điểm.

Chi tiết máy đọc: `EHRSQL_2024_PAPER_TECHNOLOGIES.json`. Nội dung bên dưới là nghiên cứu lịch sử ngày01/11, bao gồm giá/provider thời điểm đó; không dùng làm thông tin giá hiện hành.

---

# Nghiên cứu cải thiện V5 trên EHRSQL 2024 — 01/11/2026

Phạm vi của lượt nghiên cứu này: giữ dataset/database/scorer của paper; không fine-tune; không đọc câu hỏi, prediction, gold hoặc lỗi test để thiết kế thay đổi. Tài liệu này đề xuất hướng thử nghiệm, không dự đoán hoặc bảo đảm điểm tăng. Không gọi API model; chỉ đọc tài liệu công khai và code hậu xử lý hiện có.

**Hướng nên làm trước:** cải thiện binding giá trị và kiểm tra AST có bằng chứng, rồi chọn trong một nhóm policy nhỏ trên dev. V5 đã có hybrid retrieval, ba đường sinh, execution agreement và compiler ICD; thêm lại các thành phần này dưới tên công nghệ khác không phải đóng góp mới.

1. **Value grounding và ràng buộc SQL có phạm vi rõ ràng — ưu tiên cao, có thể không tốn API.**

   CHESS tách truy xuất thông tin, chọn schema, sinh ứng viên và kiểm tra truy vấn. Phần phù hợp ở đây là tìm đúng giá trị/cột và kiểm tra yêu cầu của câu hỏi; lợi ích schema pruning trong paper dành cho schema lớn không tự chuyển sang database 17 bảng của EHRSQL. Không nhập các điểm BIRD của CHESS làm kỳ vọng EHRSQL. [Paper CHESS](https://arxiv.org/html/2405.16755v3), [repo tác giả](https://github.com/ShayanTalaei/CHESS).

   Thử nghiệm đề xuất là mở rộng compiler chỉ tại các vị trí AST chứng minh được: cột phải có lineage rõ, ánh xạ dictionary duy nhất, literal phải xuất phát từ câu hỏi/metadata, giữ nguyên predicate/aggregation/time scope. Nếu không chứng minh được thì giữ SQL cũ. EQ và IN đã được V4 hỗ trợ; correlated alias cũng đã có resolver, không gọi các tính năng này là cập nhật V6. CTE/subquery projection, case và alias chỉ là các ứng viên cần kiểm tra bằng lỗi **dev** trước khi triển khai. SQLGlot hỗ trợ AST traversal/transformation nhưng chính tài liệu nêu parser không phải validator; vẫn phải chạy SQLite read-only. [SQLGlot chính thức](https://github.com/tobymao/sqlglot).

2. **Selective prediction theo metric thật — ưu tiên cao, nhưng không nới đồng thuận tùy tiện.**

   Nghiên cứu Confidence Estimation for Text-to-SQL xem consistency và execution grounding là tín hiệu hữu ích khi không có logits đầy đủ. Nó không cho phép biến “ba nhánh cùng kết quả” thành xác suất đúng đã hiệu chuẩn của EHRSQL. [Paper 2025 / công trình AAAI](https://arxiv.org/html/2508.14056v1).

   V6 nên khai báo trước một grid nhỏ: baseline V5 bất biến; các phương án chỉ chấp nhận thêm khi có 2/3 ứng viên đồng thuận **và** bằng chứng cấu trúc/contract phù hợp; có thể thêm guard loại trường hợp chắc chắn sai. Chọn bằng RS10 trên đúng dev tune, giữ coverage floor; khóa policy/hash rồi đánh giá audit và test. Một câu trả lời sai chịu phạt 10, nên không dùng tăng EX/coverage làm lý do duy nhất để nới ngưỡng. Không fit ngưỡng từ test hoặc chọn phiên bản có điểm test cao nhất.

   Một preprint tháng 7/2026 trên BIRD/Spider cho thấy consistency/executability vẫn có thể bỏ sót sai logic; judge reasoning độc lập xếp hạng correctness tốt hơn trong thí nghiệm của tác giả. Đây là bằng chứng để thận trọng, không phải kết quả được xác nhận cho EHRSQL. Một judge mới cũng thêm model, chi phí và nguồn nhiễu nên chưa phải thay đổi ưu tiên trong lượt này. [What Predicts Correctness in Text-to-SQL?](https://arxiv.org/html/2607.06799v1).

3. **Đa dạng đường suy luận đã có; tối ưu selector trước khi sinh hàng loạt ứng viên mới.**

   PromptMind là nguồn cùng shared task cho hướng ensemble tăng reliability. DAIL-SQL nghiên cứu lựa chọn ví dụ theo skeleton; V3 đã có masked-question và SQL-structure reranker nên đây là nền đã áp dụng, chưa phải cải tiến mới. [PromptMind](https://aclanthology.org/2024.clinicalnlp-1.34/), [DAIL-SQL tác giả](https://github.com/BeachWang/DAIL-SQL).

   CHASE-SQL kết hợp nhiều đường sinh và selector so cặp; selector của paper được fine-tune. Không thể gọi một prompt review bất kỳ là tái hiện selector đó. Bổ sung nhiều candidate mà không có selector tốt có thể tăng token nhưng không tăng reliability. Nếu cần inference mới, chỉ nên mở một nhánh có mục tiêu rõ trên dev trước, báo riêng ngân sách và giữ các nhánh cũ để ablation. [CHASE-SQL](https://arxiv.org/html/2410.01943v1).

4. **Đồng thuận trên một database không chứng minh tương đương ngữ nghĩa.**

   Distilled Test Suites đánh giá SQL trên nhiều database được sinh để phân biệt các truy vấn vô tình cùng kết quả. Ý nghĩa với V6 là cần test guard/compiler trên fixture có NULL, duplicates, ties, join, temporal scope và nhiều bệnh nhân; không coi result fingerprint là chứng minh đầy đủ. Không đổi database/scorer chính thức của lượt benchmark hiện tại hoặc đưa gold test vào tạo rule. [Zhong, Yu, Klein — EMNLP 2020](https://aclanthology.org/2020.emnlp-main.29/).

5. **Chưa ưu tiên PICARD, GraphRAG hoặc một vòng tự sửa ngữ nghĩa không giới hạn.**

   PICARD can thiệp từng bước decoding để loại token không hợp lệ; implementation gốc gắn với mô hình T5 và decoding có thể điều khiển. Không có bằng chứng tài liệu DeepSeek API cho phép gắn parser vào từng token theo cùng cách, nên kiểm tra AST sau generation chỉ là adaptation. [PICARD](https://aclanthology.org/2021.emnlp-main.779/). Với một database nhỏ đã có dictionary và schema đầy đủ, thêm graph/vector store mới cần ablation riêng; chưa có căn cứ cam kết tăng RS10 của hệ thống này.

**Model và chi phí được kiểm tra trên tài liệu DeepSeek ngày 01/11/2026.**

- `deepseek-flash` hiện được phục vụ bởi **DeepSeek-V4.1-Flash-1017**. Tài liệu ghi context 1M và max output 384K; đây là trần provider, không phải khuyến nghị cấp trần đó cho mỗi câu SQL. Giá off-peak mỗi 1M token: input cache miss **$0,15**, input cache hit **$0,003**, output **$0,60**; peak gấp đôi. Theo lịch công bố, Chủ nhật thuộc off-peak. Giá có thể đổi; lưu usage thực tế và model/fingerprint trả về trong run. [Models & Pricing](https://api-docs.deepseek.com/quick_start/pricing/).
- Thinking mặc định enabled, effort mặc định high. Cần tiếp tục đặt explicit enabled/disabled từng route trong request và cache key. `temperature` không có hiệu lực ở thinking mode; không tuyên bố temperature=0 làm nhánh plan tất định. [Thinking Mode](https://api-docs.deepseek.com/guides/thinking_mode/).
- Docs ghi giới hạn concurrency Flash 2.500/account và HTTP429 khi vượt; đó không phải cam kết tốc độ hoặc ngân sách tài khoản cụ thể. Worker nhỏ, bounded retry, checkpoint và budget guard vẫn cần thiết. [Rate Limit & Isolation](https://api-docs.deepseek.com/quick_start/rate_limit/).

Ước tính minh họa, không phải hóa đơn: 400 call mới, trung bình 5.000 input + 1.500 output/call, toàn input cache miss, giá off-peak hiện tại khoảng **$0,66**; ở peak khoảng **$1,32**. Thinking làm output thực tế thay đổi. Hậu xử lý trên candidate cache và renderer tiếng Anh không có API cost mới; vẫn phải báo compute generation nguồn đã trả trước.

**Đánh giá cuối nên thực hiện như sau:** khóa thay đổi/dev policy trước test; chạy đủ 1.167 câu theo official RS/EX/VSR; lưu cả V5 và V6, kể cả khi V6 kém hơn. Sau đó đưa **SQL prediction của hệ thống**, không phải gold SQL, qua execution và renderer tiếng Anh riêng để chấm full end-to-end. Controlled fact-EM kiểm tra giá trị theo grammar, còn EM/F1/ROUGE/WER đo giống từ vựng. Renderer theo mẫu là một verbalizer xác định, không phải kết quả sinh tiếng Anh tự do của LLM. Điểm English không so trực tiếp với RS của paper.

Các khuyến nghị triển khai ở trên là suy luận kỹ thuật từ các nguồn, cần được kiểm chứng bằng dev và ablation của dự án. Việc tiếp tục dùng lại test đã xem vẫn mang tính exploratory; khóa trước lần chạy mới không biến test lịch sử thành holdout độc lập.
