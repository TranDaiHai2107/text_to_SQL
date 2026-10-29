# Hướng cải thiện Text-to-SQL sau kết quả DeepSeek v2

Ngày nghiên cứu: 28/10/2026. Phạm vi chính: English → SQL, EHRSQL 2024/MIMIC-IV benchmark đã pin. Không fine-tune LLM. Không phát sinh API call hay chạy lại tác giả/Vanna trong lượt nghiên cứu này.

## 1. Kết luận để quyết định

Hệ thống còn khả năng cải thiện đáng kể. Nút thắt hiện tại là chọn SQL đúng và biết lúc nào nên từ chối; generation đã có EX 91,86%, nhưng bộ kiểm tra ngữ nghĩa làm mất nhiều đáp án đúng. Thứ tự đáng làm: tách và giữ bộ lọc thực thi → thống nhất quy ước benchmark → grounding và truy xuất cấu trúc → sinh ứng viên riêng biệt → hiệu chỉnh quyết định trả lời/từ chối.

Đây là đề xuất dựa trên code, cache và bài báo. Không hứa sẽ vượt RS10 74,21. Những phân tích dùng test hiện tại đều là hồi cứu; không thay primary đã công bố của lần chạy v2.

## 2. Số liệu thật đang chỉ ra điều gì?

Nguồn: [báo cáo v2](../experiments/ours_improved_v2/runs/deepseek_flash_v2b_20261028/FINAL_REPORT.md), [diagnostic có thể tái tạo](V2_RELIABILITY_DIAGNOSTIC_20261028.json), [script phân tích](analyze_v2_reliability.py).

- Generation v2: 1.059 đúng, 99 sai, 9 từ chối nhầm; EX 91,86%, RS10 5,91.
- Primary v2: 950 đúng, 95 sai, 122 từ chối nhầm; EX 77,94%, RS10 0,00.
- 99 câu sai generation gồm 67 câu answerable có SQL sai và 32 câu unanswerable vẫn bị trả lời.
- Bộ lọc thực thi/static trước reviewer loại 29 câu sai có kết quả rỗng: 12 unanswerable chuyển thành từ chối đúng; 17 answerable chuyển thành từ chối. Không có câu đúng nào bị bộ lọc này loại trong lần chạy đã lưu.
- Ghép lại **generation + bộ lọc có sẵn, bỏ reviewer** cho 1.071 đúng, 70 sai, 26 từ chối nhầm; EX 91,86%, RS10 **31,79**. Đây là **ablation hồi cứu trên output cố định**, không phải primary mới hay kết quả được xác nhận trên holdout mới.
- Riêng gói reviewer sau bộ lọc: 88 câu đúng thành từ chối, 46 câu đúng thành sai; chỉ cứu 13 câu sai thành đúng và 8 câu sai thành từ chối. Không nên gán công của bộ lọc thực thi cho reviewer.

Lọc kết quả rỗng là heuristic dùng trong benchmark/paper này. Ngoài benchmark, một truy vấn đúng hoàn toàn có thể có đáp án rỗng; không đồng nhất “không có bản ghi” với “schema không thể trả lời”.

RS10 = 100 × (đúng − 10 × sai) / 1.167. Mốc từ chối tất cả là 100 × 233/1.167 = **19,97**. Đây là đối chứng tối thiểu cho metric, không phải một sản phẩm hữu ích. Hai nhánh nguyên bản v2 chưa vượt mốc này; ablation guard-only hồi cứu thì vượt.

Ngay cả khi biết chính xác và từ chối cả 32 unanswerable đang bị trả lời sai, giữ nguyên mọi output còn lại, RS10 generation chỉ lên **36,08**. Đó là minh họa oracle, không phải kết quả một detector. Vì vậy chỉ thêm bộ nhận diện câu không thể trả lời sẽ chưa đủ: còn phải xử lý SQL sai trên các câu answerable.

## 3. Lỗi code/prompt và thiết kế đáng sửa trước

### 3.1 Reviewer thiếu cùng ngữ cảnh với generator và có quyền sửa quá lớn

[Generator](../experiments/ours_improved_v2/grounded_pipeline.py) nhận SYSTEM, RULES, schema/catalog và ví dụ train/dev. Reviewer chỉ nhận REVIEW, schema/catalog và SQL. SYSTEM có quy ước schema và khoảng bình thường y khoa mà reviewer không được cung cấp đầy đủ. Reviewer **đã có fixed clock**; không được kết luận lỗi do thiếu clock. Có trường hợp nó vẫn phản bác SQL đúng với quy ước benchmark.

Các ví dụ đã kiểm tra, chỉ dùng chẩn đoán hậu nghiệm:

- `0298d7de83dc23f17441f202`: SQL đúng theo năm lịch trước bị reviewer yêu cầu đổi thành 365 ngày gần nhất.
- `350a9469b2c148343a897fc7`: SQL đúng bị đổi quy ước DENSE_RANK/ties, thêm cột đếm và đổi mốc thời gian.
- `666e67f82411b8a3b4b429e7`: truy vấn đúng về emergency room bị từ chối vì catalog truy xuất không xác nhận một giá trị trong admissions.

**Đề xuất:** giữ ứng viên ban đầu bất biến. Reviewer chỉ xuất đề xuất có loại lỗi và bằng chứng; không tự ghi đè. SQL lỗi cú pháp/column có thể sửa có giới hạn. Bất đồng về ý nghĩa phải tạo ứng viên B và chuyển sang bước chọn/abstain. Cùng một tài liệu semantic convention phải đi vào mọi đường sinh/kiểm tra.

### 3.2 Tài liệu quy ước benchmark cần thành một phần có phiên bản

Cần mô tả từ train/dev: năm lịch so với trailing interval, định dạng thời gian kiểu `this month/07`, current/completed/first/last admission, mốc nhập viện hay ICU, ties trong xếp hạng, precision, đơn vị, output columns, ánh xạ cost.event_type.

Ví dụ lỗi hiện có: `fed90306e7ed0344ed0a3b7d` hiểu day 07 thành tháng 7; `741720ef5045654c9099edd9` hiểu current visit thành admission mới nhất, đồng thời làm tròn ngày phân số. Đây là quy ước của dataset; không tuyên bố gold SQL là cách hiểu lâm sàng duy nhất trong mọi hoàn cảnh.

Không mã hóa ID/đáp án test vào quy tắc. Mỗi quy tắc mới phải có nguồn metadata hoặc ví dụ train/dev và test nhỏ cho boundary dates, NULL, ties, nhiều admissions.

### 3.3 Grounding phải trả cả bảng, cột, giá trị và nguồn

Catalog hiện có item/ICD/microbiology nhưng thiếu nhiều enum như `cost.event_type`, admission_location/type, route, careunit. Top 10 nhãn truy xuất chỉ là danh sách ứng viên; không tìm thấy trong top 10 không chứng minh database thiếu thông tin.

Ví dụ chẩn đoán: `49696e268e9abaecd49791d8` chọn icustays thay vì transfers cho careunit; `3de8ef9d5ffcc52173897ea8` chọn `height` thay vì `height (cm)`; `52015439c33be0dc487387d4` dùng giá trị cost event không đúng.

**Đề xuất:** normalized exact match trước, BM25/fuzzy/embedding sau. Mỗi concept trả `table.column`, itemid/value, linksto, đơn vị/abbreviation nếu metadata có, và ambiguity nếu nhiều bảng phù hợp. Metadata dùng để định vị khái niệm, không phải bằng chứng khẳng định bệnh nhân có sự kiện đó. Giữ full schema 17 bảng; chưa cần thêm agent cắt schema mạnh.

### 3.4 Output cũng cần một contract rõ ràng

13/67 lỗi answerable generation có output hai cột trong khi gold một cột. Một phép kiểm tra oracle bỏ cột dư/ORDER BY cứu được 8 trường hợp; đó không phải kết quả sửa tự động, vì phép chẩn đoán đã dùng gold. Ví dụ `4b72e7b13c37b47053d926d9` trả cả month và MAX(value), trong khi gold chỉ trả MAX(value) theo từng nhóm tháng.

**Đề xuất:** plan gồm `requested_fields`, `aggregation`, `grouping`, `output_cardinality`, `ordering`, `limit`, `patient`, `visit_scope`, `time_reference`, `clinical_concepts`. SQLGlot kiểm tra phần xác minh được. Không tự bỏ cột chỉ để khớp test; suy ra contract từ câu hỏi và quy ước train/dev. Contract do LLM tạo vẫn có thể sai.

## 4. Các bài báo phù hợp và giới hạn áp dụng

### A. PromptMind, EHRSQL 2024 — bằng chứng trực tiếp nhất

[PromptMind Team at EHRSQL-2024: Improving Reliability of SQL Generation using Ensemble LLMs](https://aclanthology.org/2024.clinicalnlp-1.34.pdf) cho các model sinh SQL riêng, so kết quả thực thi. Table 3: GPT-4 + Claude-3 Opus không fine-tune đạt RS10 **65,72**. Mốc **74,89** của cả ba có GPT-3.5 fine-tuned, không gán cho cấu hình không fine-tune. Mượn cách đối chiếu ứng viên; không coi đồng thuận là ground truth. Đây là model/cấu hình lịch sử, không cam kết endpoint cũ còn khả dụng.

### B. DAIL-SQL — truy xuất theo cấu trúc thay vì chỉ câu giống nghĩa

[Paper](https://arxiv.org/html/2308.15363v3), [repo tác giả](https://github.com/BeachWang/DAIL-SQL): lựa chọn ví dụ sử dụng câu hỏi đã che thực thể và SQL skeleton; có self-consistency. Đề xuất dùng SQL đầu tiên của mình làm bản sơ bộ để rerank KB theo COUNT/GROUP BY/rank/subquery/temporal structure. Không thêm tầng RAG chỉ để tăng số tầng. Các số Spider của paper không dự báo điểm EHRSQL.

### C. CHESS và CHASE-SQL — mượn thành phần, không dựng toàn bộ ngay

[CHESS](https://arxiv.org/abs/2405.16755), [repo](https://github.com/ShayanTalaei/CHESS): hữu ích cho value retrieval và kiểm tra ứng viên. Bản ngân sách cao có nhiều candidates/tests; một số cấu hình chi phí thấp dùng model fine-tuned. Không gọi toàn bộ framework là không fine-tune.

[CHASE-SQL](https://arxiv.org/abs/2410.01943) dùng các đường sinh đa dạng như decomposition/query plan; hệ thống đầy đủ có selector fine-tuned. Mượn cách tạo B/C, không gán mốc BIRD 73% cho bản adaptation DeepSeek của mình.

### D. Confidence cho API đóng: consistency và mệnh đề SQL

[Confidence Estimation for Text-to-SQL in Large Language Models, AAAI 2026](https://ojs.aaai.org/index.php/AAAI/article/view/40523): consistency là hướng mạnh trong nhóm black-box được nghiên cứu; thực thi bổ sung tín hiệu. Phù hợp để thử agreement thay logprob hằng số, chưa chứng minh hiệu quả trên EHRSQL của mình.

[Calibrating LLMs for Text-to-SQL Parsing by Leveraging Sub-clause Frequencies, preprint 2025](https://arxiv.org/html/2505.23804v1): dùng tần suất mệnh đề và multivariate Platt scaling. Có thể thử tỷ lệ đồng thuận SELECT/WHERE/JOIN/thời gian rồi fit calibrator nhỏ. Đó không phải fine-tune LLM; bản API sampling-only cũng không tái hiện đầy đủ beam-search của paper.

[Confidence Estimation for Error Detection in Text-to-SQL Systems, AAAI 2025](https://ojs.aaai.org/index.php/AAAI/article/view/34699): uncertainty thường dễ bắt câu không liên quan hơn SQL sai. Cần tách answerability và SQL correctness.

### E. RTS++ và DPC — hướng sau khi có consensus cơ bản

[Reliable End-to-End Text-to-SQL Generation, EDBT 2026](https://openproceedings.org/2026/conf/edbt/paper-177.pdf) dùng execution entropy/conformal calibration. Mốc 92,3/92,5% là selective accuracy trong thiết lập Spider/BIRD có human feedback; không dùng làm EX toàn bộ EHRSQL. Chỉ mượn nhóm kết quả/entropy; không hứa bảo đảm đúng cho mọi câu được trả lời hay tái hiện API-only toàn bộ RTS++.

[DPC: Training-Free Text-to-SQL Candidate Selection via Dual-Paradigm Consistency, ACL 2026](https://aclanthology.org/2026.acl-long.313/) dùng DB tổng hợp nhỏ để phân biệt SQL, đối chiếu thêm đường giải Python/Pandas. Phù hợp kiểm tra first/last, joins, grouping khi hai ứng viên cùng kết quả trên DB thật. Đường giải Python vẫn là proxy có thể sai; chưa nên dựng cả framework ngay.

[Semantic Evaluation for Text-to-SQL with Distilled Test Suites, EMNLP 2020](https://aclanthology.org/2020.emnlp-main.29/) giải thích vì sao cùng kết quả trên một DB chưa chứng minh cùng ngữ nghĩa. Test bổ sung chỉ để kiểm tra phương pháp; giữ nguyên official EHRSQL scorer khi so paper.

Một [preprint tháng 7/2026 về selective prediction](https://arxiv.org/abs/2607.06799) còn ghi nhận lợi thế của các verifier mạnh từ nhiều provider trong thiết lập khác. Điều này không phủ nhận thất bại reviewer hiện tại, và cũng cho thấy không thể xem consistency là oracle. Chưa dùng kết quả preprint đó để hứa điểm cho hệ thống này.

## 5. Kiến trúc đề xuất v3, không fine-tune LLM

Các bước sau là thiết kế đề xuất của dự án, chưa triển khai/chạy model trong lượt nghiên cứu này.

1. **Generator A:** giữ generation đã cải thiện, schema đầy đủ, metadata đúng bảng/cột và truy xuất train/dev. Bộ lọc thực thi/static là thành phần riêng, có ablation.
2. **Semantic contract:** giữ thực thể, bệnh nhân, output, visit/time scope, aggregation và ties. Không rewrite câu đơn lẻ chỉ để đổi cách diễn đạt. Không lấy nhận xét tự do của reviewer làm bằng chứng sửa.
3. **Generator B:** sinh từ structural retrieval/plan; không cho B đọc SQL A trước khi sinh. B dùng cùng backbone cho phép thử đóng góp phương pháp. Model khác là một ablation riêng, phải báo chi phí.
4. **Execution grouping:** chạy read-only; nhóm ứng viên bằng dấu vân tay kết quả và thông tin output. Error không phải một nhóm đồng thuận hợp lệ; hai empty result cũng không đủ chứng minh đúng. So sánh toàn bộ kết quả trong budget, giữ số cột, NULL và multiplicity; không chỉ so 100 dòng đầu/round3 như scorer. Scorer chính thức vẫn dùng chuẩn hóa gốc.
5. **Risk features:** agreement giữa ứng viên, bất đồng từng mệnh đề, ambiguity của entity mapping, contract thiếu/đổi điều kiện, khoảng cách truy xuất, số lượt sửa. Không dùng lời tự khai “tôi chắc chắn” làm xác suất.
6. **Quyết định đã khóa:** một nhóm đáng tin và đạt ngưỡng đã chọn trên calibration thì trả SQL; nếu bất đồng không giải quyết được thì `null`. Đối thoại làm rõ chỉ là chế độ ứng dụng, không giả định benchmark cho phép hỏi thêm người chấm.
7. **Cascade:** ban đầu đo hai đường sinh trên dev. Chỉ sau khi có bằng chứng mới routing thêm B/C cho phần câu khó; không mở 20 candidates theo mặc định. Một lượt T=0, cùng prompt lặp lại thường trùng cache/không tạo đa dạng hữu ích.

Nếu 30% câu cần thêm hai generator, số lượt sinh dự kiến là 1.167 × (1 + 2 × 0,3) ≈ **1.867**, chưa tính plan/sửa. Đây là kịch bản tính toán, không là số đo hay cam kết chi phí. So với 2.524 API calls test hiện tại còn phải xét độ dài prompt, cache, latency và routing errors.

## 6. Calibration và thiết kế thí nghiệm để bảo vệ được trong KLTN

- Không cần bác sĩ chấm từng câu English→SQL benchmark: có thể tạo nhãn đúng/sai cho calibration bằng chạy SQL và so gold answer theo scorer. Bác sĩ vẫn cần cho khẳng định tính phù hợp lâm sàng ngoài benchmark; một scalar EX không xác nhận phần đó.
- Có thể giữ yêu cầu train+dev làm KB cuối cùng. Khi đó cần calibration mới độc lập hoặc cross-fitting có phân nhóm: fold được chấm không xuất hiện trong index, loại cả câu trùng/template nếu đang đánh giá generalization theo nhóm. Chỉ bỏ chính ID như v2 chưa tạo được một tập hoàn toàn ngoài knowledge.
- Track gần điều kiện paper hơn: train làm KB, dev tách tune/calibration/audit; không dùng câu audit để chọn lại cấu hình. Đây là track bổ sung được đề xuất, chưa đổi KB train+dev hiện tại.
- Cross-fitting với các index khác nhau không tự tạo bảo đảm conformal cho final index. Muốn nói đến formal guarantee cần kiểm tra giả thiết exchangeability, calibration protocol và khác biệt phân phối; trước mắt nên gọi là hiệu chỉnh thực nghiệm.
- Test hiện đã được xem để thiết kế. Thay seed, chạy nhiều lần hay tạo folder mới không làm test trở lại độc lập. Giữ số cũ, ghi exploratory cho cải thiện này; dùng holdout mới hoặc protocol đánh giá được khóa để xác nhận tổng quát.
- Giữ model, schema, DB, KB, scorer, split, token budget rõ giữa đối chứng. Nếu thêm model mạnh hoặc nhiều calls, cần ablation tách tác động model và compute khỏi phương pháp.

Metrics cần giữ: RS0/RS5/RS10/RSN, EX/934, VSR với định nghĩa rõ, coverage, precision trong các câu trả lời, wrong-answerable, false-answer-unanswerable, false-abstention, correct→wrong/abstain do sửa, token/calls/latency. Khi sinh nhiều candidates thêm candidate coverage/pass@K và selector accuracy để biết thiếu ứng viên đúng hay chọn sai; gold chỉ dùng offline đánh giá.

Riêng câu chắc chắn answerable, một quyết định với xác suất đúng p có kỳ vọng trả lời `p − 10(1−p)`; vượt abstain=0 khi p > 10/11 ≈ 90,91%. Đây không phải ngưỡng chung cho EHRSQL vì từ chối đúng unanswerable được +1 và xác suất phải được hiệu chỉnh. Chọn ngưỡng cuối bằng RS10 trên calibration kèm coverage, không tùy chọn bằng test.

## 7. Thứ tự xây dựng nên chọn

**P0 — Sửa thành phần đang gây hại:** tách reviewer khỏi quyền ghi đè; giữ guard riêng; hợp nhất benchmark conventions. Chi phí thêm model gần như không có. Kiểm tra lại trên dữ liệu phát triển trước khi khẳng định lợi ích.

**P1 — Làm generator có chứng cứ hơn:** mở rộng categorical metadata, masked/structural retrieval, output/time/visit contract. Dùng template từ train/dev, không hardcode lỗi test. Không thêm tầng RAG hay schema-pruning agent chỉ vì tên kiến trúc.

**P2 — Cải thiện quyết định trả lời:** hai đường sinh, execution agreement, detector answerability tách riêng, calibrator không phụ thuộc logprob. Calibrator logistic nhỏ là tùy chọn; nếu không muốn huấn luyện bất kỳ model nào, bắt đầu bằng grid rule đã khóa trên calibration.

**P3 — Kiểm tra logic khó:** dùng fixture/MDD cho ties, NULL, nhiều admissions, ranh giới thời gian. Chỉ mở rộng nếu P0–P2 chứng minh hiệu quả theo RS10/coverage/cost.

Chưa ưu tiên: dựng nguyên CHESS/CHASE, fine-tune LLM, reviewer mạnh sửa mọi câu, lặp cùng prompt T=0 nhiều lần, đổi benchmark để tìm điểm đẹp, hay làm ASR/dịch/SQL-to-text nhằm tăng RS10. Những phần ngoài SQL cần metric và đánh giá riêng.

## 8. Phần chưa biết cần kiểm chứng

Chưa có số đo tương lai cho v3; chưa xác định consensus/structural retrieval sẽ cứu được bao nhiêu lỗi trong 67 answerable sai. DeepSeek API mô tả logprob trong [tài liệu chính thức](https://api-docs.deepseek.com/api/create-chat-completion/) nhưng không nói rõ logprob trước/sau temperature. Cache v2 toàn 0 là quan sát thực nghiệm; chưa chứng minh temperature=0 là nguyên nhân. Nếu muốn dùng lại tín hiệu này, cần probe nhỏ ngoài benchmark ở vài cấu hình rồi kiểm tra biến thiên trước khi chạy lớn.

Mốc đề xuất trước mắt: vượt đối chứng từ chối tất cả với coverage hữu ích, giảm số câu sai ở mức EX được báo đầy đủ, và reviewer không phá câu đúng. Mốc paper 74,21 là mục tiêu nghiên cứu tiếp, không phải lời hứa của bản thiết kế.
