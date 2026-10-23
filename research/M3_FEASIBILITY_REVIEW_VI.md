# Thẩm định M3 để đánh giá KLTN tiếng Anh → tiếng Anh

Ngày kiểm tra: 12/10/2026. Phạm vi: nghiên cứu tài liệu, kiểm tra dữ liệu công khai và thực thi Gold SQL chỉ đọc; chưa chạy mô hình hoặc hệ thống của sinh viên trên benchmark, chưa phát sinh chi phí API.

## Kết luận

**Có thể dùng M3 làm nghiên cứu đối chiếu cho KLTN.** Dataset là EHRSQL 2024; M3 là hệ thống và giao thức đánh giá trên một mẫu của dataset đó. Hướng này phù hợp hơn việc ghép một benchmark Text-to-SQL với benchmark diễn đạt ý nghĩa SQL.

Đã kiểm chứng được phần cốt lõi để bắt đầu: câu hỏi, gold, database, nhãn kết quả từng mẫu và đầu ra văn bản của hai baseline đều có. Việc chạy thử Gold SQL đã thành công. Tuy nhiên, hệ thống hiện tại cần một profile benchmark riêng trước khi chạy; con số accuracy do người chấm của M3 không phải EX tự động. Muốn tuyên bố hệ thống tốt hơn cần cùng dữ liệu, cùng rubric, và chấm lại đầu ra baseline cùng đầu ra của mình.

## 1. Bài báo và tài liệu đã kiểm tra

M3: Conversational LLMs simplify secure clinical data access, understanding, and analysis; PLOS Digital Health 5(9), e0001671; xuất bản 17/09/2026. Bài dùng EHRSQL, đánh giá câu trả lời có đáp án và khả năng từ chối câu không trả lời được. SQL và câu trả lời cuối được hội đồng kỹ thuật/lâm sàng đối chiếu về ngữ nghĩa; không yêu cầu khớp câu văn.

- [Bài báo chính thức](https://journals.plos.org/digitalhealth/article?id=10.1371%2Fjournal.pdig.0001671).
- [S1: Claude](https://journals.plos.org/digitalhealth/article/file?type=supplementary&id=10.1371/journal.pdig.0001671.s001).
- [S2: gpt-oss](https://journals.plos.org/digitalhealth/article/file?type=supplementary&id=10.1371/journal.pdig.0001671.s002).
- [S3: unanswerable](https://journals.plos.org/digitalhealth/article/file?type=supplementary&id=10.1371/journal.pdig.0001671.s003).
- [Repository M3](https://github.com/rafiattrach/m3).
- [Repository EHRSQL](https://github.com/glee4810/ehrsql-2024).

Đã tải toàn văn PLOS bằng HTTP từ nguồn chính thức, đọc các phần phương pháp, kết quả, giới hạn và phụ lục; tải cả S1–S3; clone mã nguồn và xem lịch sử thay đổi. Các lỗi đọc trang qua web tool không được dùng để suy đoán nội dung.

## 2. Bằng chứng kiểm tra độc lập trên file thực tế

Các kết quả dưới đây là phép đếm/đối chiếu offline, được lưu trong `m3_audit_manifest.json`, tái lập bằng `audit_m3.py`.

- S1: 100 câu, 94 nhãn đúng và 6 nhãn sai.
- S2: 100 câu, 93 nhãn đúng và 7 nhãn sai.
- S3: 100 câu, 69 nhãn đúng và 31 nhãn sai.
- Hai nhóm có đáp án dùng cùng một tập 100 câu. Đếm ghép cặp: cả hai đúng 90; chỉ Claude đúng 4; chỉ gpt-oss đúng 3; cả hai sai 3.
- Sau chuẩn hóa Unicode/khoảng trắng, ba CSV ở repository khớp ba supplementary CSV đã xuất bản, gồm cả câu hỏi, gold, đầu ra và nhãn. Khác byte ban đầu chủ yếu là ký tự khoảng trắng và xuống dòng, không phải thay đổi kết quả.
- Có đủ 100 transcript gpt-oss cho nhóm có đáp án và 100 transcript cho nhóm không có đáp án. Claude có các liên kết hội thoại chia sẻ; chưa kiểm chứng tính truy cập của toàn bộ 100 liên kết đó. Các CSV vẫn có đầu ra cuối và nhãn.
- Mỗi câu ở cả hai nhóm 100 được ánh xạ về một ID của EHRSQL v1.0.5 bằng khớp nguyên văn; không dùng fuzzy matching để quyết định gold.
- Toàn bộ 100 Gold SQL của mẫu có đáp án thực thi được bằng SQLite chỉ đọc, và khớp đáp án chính thức đã lưu: 100/100, không lỗi thực thi hay mismatch trong lần kiểm tra này.

Đây là kiểm tra tính sẵn sàng của dữ liệu, không phải kết quả mô hình của sinh viên. Số 94/93/69 chỉ được đếm lại từ nhãn tác giả, chưa được một hội đồng độc lập chấm lại.

## 3. Phiên bản phải đóng băng

Snapshot tải về của M3:

`72b107576bee38544848bab58200222951e8cece`

EHRSQL v1.0.5, phiên bản đã đối chiếu khớp mẫu của M3:

`2cf205a4673d96bafcb0310cc725cbe6168544da`

[Snapshot EHRSQL v1.0.5](https://github.com/glee4810/ehrsql-2024/tree/2cf205a4673d96bafcb0310cc725cbe6168544da).

Snapshot EHRSQL hiện tại đã tải trước đó:

`f9e1aa02160d39e3f8df52bf5c69c5cf2e472499`, test v1.1.2.

Đối chiếu lịch sử phát hiện:

- Mẫu có đáp án khớp nguyên văn 100/100 câu với v1.0.5, nhưng 94/100 với v1.1.2.
- Có 6 câu thay đổi văn bản và 24 câu thay đổi chuỗi SQL; hợp hai nhóm là 26 mẫu có thay đổi. Thay đổi chuỗi SQL không tự chứng minh khác kết quả thực thi; bản mới đã có sửa cách hỏi/nhãn.
- Database SQLite ở hai snapshot có cùng SHA256. Sự khác nhau nằm ở annotation, không phải khác byte database trong hai bản đã kiểm tra.
- V1.0.5 được xác nhận phù hợp bằng nội dung mẫu/gold, không phải tuyên bố tác giả cung cấp exact commit của môi trường chạy.

Do đó, khi so với 94/93, giữ nguyên 100 câu và gold của M3/v1.0.5. Khi mở rộng lên toàn bộ test mới, báo cáo thành thí nghiệm riêng với phiên bản khác.

## 4. Có input tiếng Anh và output tiếng Anh để chấm không?

**Có input câu hỏi và có đầu ra tiếng Anh đã công bố của baseline. Có gold dữ liệu để kiểm tra độ đúng của đầu ra.** Nhưng baseline answer không phải gold prose: không được lấy câu trả lời Claude/gpt-oss làm đáp án chuẩn.

Các CSV có Query, Model Answer, Golden Truth, Golden Truth SQL Query, Correct/Incorrect và ghi chú lỗi. Golden Truth thường là số, ngày hoặc danh sách giá trị. Không có một câu văn chuẩn duy nhất cho mỗi mẫu.

Điều này đủ cho đánh giá đầu cuối bằng ý nghĩa: một câu trả lời đúng phải chứa thông tin đúng theo gold, trả lời đúng yêu cầu và không thêm khẳng định không được dữ liệu hỗ trợ. Không cần nội bộ của hệ thống giống M3 hoặc phải dùng MCP. Tuy nhiên, đây là chấm đúng nội dung truy xuất, không chứng minh tư vấn y khoa an toàn hoặc lời khuyên điều trị đã được bác sĩ xác nhận.

Ví dụ thực tế CSV: câu hỏi yêu cầu ID bệnh nhân có chẩn đoán cataract extraction status, gold là `10025612`; câu trả lời tiếng Anh chứa đúng ID có thể được đánh giá dù khác cách diễn đạt. ID này thuộc demo đã được công bố, không phải ví dụ tự dựng.

## 5. Vì sao 94% không thể gọi là EX của hệ thống M3?

M3 dùng nhãn người chấm; EX của EHRSQL dùng đối chiếu kết quả thực thi. Audit phát hiện một tình huống minh họa rõ ràng:

- Mẫu thứ nhất có gold liệt kê 23 tên thuốc.
- Hai đầu ra baseline đều trình bày 5 thuốc và cùng nhận nhãn đúng.
- Gold dùng DENSE_RANK; các hạng có thể đồng hạng và trả hơn 5 phần tử. Đầu ra mô hình chọn 5 tên không tương đương toàn bộ tập gold.

Đây là một cờ cần xem xét khi xây rubric và chấm lại, chưa phải kết luận toàn bộ annotation sai. Không được tự điều chỉnh một mẫu rồi vẫn gọi điểm mới là điểm chính thức của bài.

Hệ quả: nếu hệ thống đạt EX tự động 90%, không thể nói nó kém M3 94% do chấm hai thứ khác nhau. Nếu thay người chấm bằng LLM judge, điểm mới cũng không trực tiếp tương đương bảng M3. Nếu dùng rubric nghiêm ngặt hơn, chấm lại cả đầu ra baseline và đầu ra của mình với rubric đó.

## 6. Những giới hạn tái lập đã thấy trong artifact

### Ngân sách tương tác khác nhau

Đếm transcript gpt-oss của 100 câu có đáp án: 410 lần gọi `execute_mimic_query`, trung bình 4,1/câu, khoảng 1–17/câu. Trong đó có thăm dò và kiểm tra, không phải tất cả đều là query cuối. M3 dùng một tác tử có thể khám phá schema/giá trị bằng công cụ; hệ thống hiện tại có một query ban đầu và tối đa hai lần sửa lỗi.

Có 99 transcript một lượt người dùng và một transcript có thêm lượt `what was the 4th?`. Không được mặc định mọi transcript là đầu ra chỉ từ đúng một prompt. Cần xem xét mẫu này và quy định rõ trạng thái hội thoại khi chấm lại; nếu loại mẫu, phải loại cho tất cả hệ thống và báo điểm trên 99 câu, không dùng 94/100 làm điểm cùng giao thức.

### Open weights chưa đồng nghĩa chạy xác định

Artifact gpt-oss có contextLength 32000 và temperature 0.8; chưa tìm thấy seed trong các trường đã kiểm tra. Vì vậy không lặp lại khẳng định rằng chỉ cần model open weights là chạy ra y hệt. Phải ghi model file/hash, engine, sampling, seed nếu có, tool definitions và ngân sách. Nên chạy lặp hoặc báo cáo biến động nếu đủ ngân sách.

### Mã nguồn hiện tại đã thay backend

Main hiện tại dùng DuckDB/Parquet, còn thí nghiệm mô tả SQLite. Lịch sử cho thấy chuyển local backend sang DuckDB vào tháng 10/2025. Commit `7faccefd92d9aa24b79fa6dd748d5835c1df49f0` (01/10/2025) chứa kết quả gpt-oss và code SQLite; đây là ứng viên để tái lập, chưa chứng minh chính là exact runtime commit tác giả đã dùng.

### Nhãn human review là một nguồn sai số

Những lời giải hợp lý khác nhau, đồng hạng, đơn vị và bổ sung ngoài dữ liệu cần quy tắc trước. Hội đồng kiểm tra câu trả lời trong nghiên cứu không đồng nghĩa kiểm định toàn bộ dataset cho sử dụng lâm sàng. Không có bằng chứng hiện tại đủ để gọi bộ này là chuẩn vàng lâm sàng tuyệt đối.

## 7. Những phần phải thích nghi trong repo của sinh viên

Đây là kết luận từ đọc code hiện tại, không phải đề xuất thay kiến trúc KLTN.

1. **Database/schema:** tạo profile EHRSQL SQLite riêng. Không chạy benchmark trên MIMIC-IV Mini 3.1 hiện tại. Database audit có 17 bảng và 94 bệnh nhân sau preprocessing; bài mô tả nguồn demo 100 bệnh nhân. Giữ đúng file benchmark, không tự bổ sung 6 bệnh nhân. Ví dụ khác biệt gồm `admissions.age`, `diagnoses_icd.charttime`, bảng `cost` và ICD dạng `icd9|4139`. MIMIC-IV schema gốc 31 bảng không tương đương schema này.
2. **Dialect và validator:** `run_query()` hiện parse PostgreSQL, dùng transaction PostgreSQL và schema hiện tại. Validator còn yêu cầu ICD join với `icd_version`, trong khi benchmark gộp phiên bản vào mã và không có cột đó. Cần validator theo profile; không tắt toàn bộ kiểm tra chỉ để SQL benchmark chạy.
3. **English mode:** `generate_sql`/`interpret_result` hiện có chỉ dẫn tiếng Việt; câu trả lời rỗng và fallback cũng tiếng Việt. Cần chuyển cả prompt và fallback sang tiếng Anh cho phase này, không dùng thêm dịch thuật rồi gọi đó là thí nghiệm English-only.
4. **Clock:** cố định mốc 2100-12-31 23:59:00, xử lý các biểu thức tương đối nhất quán với EHRSQL. Không dùng thời gian thật của máy.
5. **Bảo toàn kết quả:** mặc định `_build_metadata_summary()` gộp numeric nhiều dòng thành min/max/mean/sum và text thành top 5. Điều này mất danh sách ID/ngày/thuốc đầy đủ. Chế độ raw cũng chỉ gửi 20 dòng, trong khi một gold mẫu có 23 dòng. Module trả lời cần nhận đủ bằng chứng phù hợp; có thể xử lý kết quả tại chỗ và dùng renderer xác định cho ID/danh sách. Chính sách dữ liệu của dự án vẫn cần được giữ khi chọn nơi chạy model.
6. **Abstention:** phải phân biệt không thể trả lời từ schema với truy vấn có kết quả rỗng. Một empty result hợp lệ không tự biến câu thành unanswerable. Thêm đầu ra có cấu trúc như status/answer/sql để chấm được từ chối; không chỉ xử lý lỗi SQL.
7. **Evaluator:** `evaluate.py` chỉ chấm SQL, chưa gọi `interpret_result`. Cần log câu trả lời cuối và toàn bộ attempt. Nó còn loại lỗi dự đoán khỏi mẫu số EX khi execution_match=None, loại empty gold, làm tròn sáu chữ số và sắp xếp riêng các giá trị trong hàng. Đây không phải bộ chấm EHRSQL. Khi so sánh, dùng scorer chuẩn; các thất bại phải hiện trong mẫu số đúng giao thức.
8. **Leakage:** Gold SQL/answer, đầu ra baseline và ghi chú test chỉ dành cho chấm. RAG/few-shot chỉ dùng train hoặc nguồn không chứa holdout. Kho 101 ví dụ hiện là tiếng Việt theo schema khác nên cần kiểm tra tương thích và trùng lặp ngữ nghĩa, không chỉ so chuỗi tiếng Anh.

## 8. Giao thức thực nghiệm tôi đề xuất

Các bước sau là thiết kế đề xuất, không phải quy định nguyên văn của M3.

### Thí nghiệm chính: same-sample end-to-end QA

- Tập A: đúng 100 câu có đáp án của M3.
- Tập U: đúng 100 câu không có đáp án của M3, báo cáo riêng.
- Database/profile: v1.0.5 SQLite đã pin; clock cố định.
- Reset hội thoại cho mỗi câu. Giữ RAG, sửa lỗi trong hệ thống; ghi lại budget, tool calls, tokens, runtime.
- Input model chỉ có câu hỏi và nguồn được phép; hoàn toàn không đưa gold hoặc baseline answer vào prompt.
- Output cần lưu SQL cuối, kết quả truy vấn, answer tiếng Anh, status, attempts và lỗi. Tool outputs được lưu để người chấm biết căn cứ của câu trả lời.
- Dùng baseline M3 đã công bố làm mốc lịch sử. Để so sánh vững hơn, chấm lại published answers của M3 và outputs của mình với cùng rubric, ẩn tên hệ thống, thứ tự ngẫu nhiên.
- Khi có điều kiện, mỗi mẫu được hai người chấm độc lập, ít nhất một người kỹ thuật và một người có chuyên môn lâm sàng; xử lý bất đồng bằng người thứ ba/đồng thuận. Nếu chỉ có người chấm kỹ thuật, công bố giới hạn, không gọi là tái lập đầy đủ hội đồng lâm sàng M3.
- Các mẫu gây mơ hồ phải có quy tắc công khai, không sửa gold sau khi xem lỗi hệ thống mà không báo thay đổi.

### Rubric và chỉ số

- **Answer correctness:** tỷ lệ câu trả lời cuối đúng, đủ thông tin yêu cầu, không có khẳng định bổ sung sai/không căn cứ. Mẫu số gồm tất cả câu ở A, kể cả model fail/timeouts. Mức cho phép rounding/units/ties phải quy định trước.
- **Joint correctness:** đồng thời truy vấn hợp lệ về ý nghĩa và câu trả lời cuối đúng. Chấm riêng trường hợp SQL sai nhưng tình cờ ra đúng dữ liệu trên demo. Nếu chỉ kiểm tra câu trả lời mà bỏ SQL, phải gọi là thí nghiệm thay đổi giao thức.
- **EX trên A:** dùng chuẩn hóa của scorer EHRSQL, báo đúng phạm vi 100 câu; chưa có baseline EX chính thức của M3 để đối chiếu. Không lấy query cuối trong transcript một cách máy móc vì query cuối có thể là thăm dò/kiểm tra.
- **VSR trên A:** số câu có SQL cuối chạy thành công/N. Có thể thêm first-attempt VSR và after-correction VSR. Không trình bày là metric M3 công bố.
- **Correct abstention trên U:** từ chối trả lời đúng/N; empty result, trả lời ngoài schema hoặc hỏi lại như thể có thể trả lời không tự được tính đúng. Không trộn A/U theo tỷ lệ 50/50 để gọi là điểm EHRSQL full test.
- **Latency/cost/attempts:** chỉ số phụ giúp so sánh ngân sách tương tác. Vì paper không cung cấp đầy đủ chi phí/latency để đối chiếu, cần chạy lại baseline cùng môi trường nếu muốn kết luận về hiệu quả tính toán.
- **Thống kê:** Wilson 95% CI cho các tỷ lệ; McNemar exact cho outcomes ghép cặp trên cùng câu. Chỉ cao hơn 1–3 điểm trên 100 câu chưa tự chứng minh khác biệt có ý nghĩa. Nếu chấm lại nhãn baseline, dùng nhãn mới cho paired test và giữ điểm công bố riêng.
- Không dùng WER để chấm QA tiếng Anh; WER thuộc nhận dạng lời nói. Không dùng BLEU làm bằng chứng chính cho tính đúng của số liệu/ID.

### Thí nghiệm phụ: khả năng truy xuất và ablation

- Dùng validation riêng để chọn model/prompt và quota policy, không tune trên 100 câu M3.
- Freeze cấu hình trước khi chạy holdout; ablation cần cùng model, dữ liệu và budget. Một bảng so model khác nhau là so hệ thống tổng thể, không cô lập đóng góp RAG.
- Giữ các chế độ base/icd/schema/examples/full; nếu muốn chứng minh Validator, Agentic và Rewrite thì bổ sung đối chứng tương ứng, tránh gọi bảng chỉ RAG là đủ cho mọi đóng góp.
- Khi đủ ngân sách, chạy toàn bộ EHRSQL test phiên bản đã chọn, dùng scorer Reliability Score chính thức cho cả answerable/unanswerable. Ghi rõ đây là scope khác mẫu M3.
- Hội thoại đa lượt và MIMIC-IV Mini 3.1 được đánh giá riêng. Mẫu M3 không chứng minh toàn bộ 31 bảng hoặc multi-turn của khóa luận.

## 9. EHRXQA có cần dùng ngay không?

[EHRXQA, NeurIPS 2023](https://papers.neurips.cc/paper_files/paper/2023/file/0c007ebef1d11fd48da6ce4f54687db6-Paper-Datasets_and_Benchmarks.pdf) có phần Table-related QA phù hợp, baseline BM25/ChatGPT đạt Prediction Execution Accuracy 92,9% và Logical Form Accuracy 73,0%. Nó là lựa chọn phụ cho truy xuất, nhưng điểm trên đó không tương đương chấm diễn giải câu trả lời M3.

Với KLTN hiện tại, tôi ưu tiên EHRSQL + M3 trước để giảm công việc thích nghi và giữ mục tiêu đầu cuối rõ ràng. EHRXQA chỉ nên bổ sung sau khi profile và evaluator chính đã ổn định; phần ảnh X-quang nằm ngoài pipeline bảng hiện tại.

## 10. Mức độ sẵn sàng và cách phát biểu kết quả

**Đủ cơ sở để chọn hướng nghiên cứu:** có bài xuất bản, mẫu cố định, gold, database và đầu ra đối chứng công khai; đã kiểm chứng được phần dữ liệu/thực thi.

**Chưa sẵn sàng chạy ngay nguyên code hiện tại:** còn adapter SQLite/schema, English mode, evaluator đầu cuối, bảo toàn kết quả và abstention.

**Chưa có bằng chứng hệ thống sinh viên tốt hơn M3:** chưa chạy model, chưa chấm độc lập và chưa kiểm tra thống kê. Thí nghiệm khả thi không bảo đảm vượt 94%.

Phát biểu phù hợp cho đề cương:

> Giai đoạn tiếng Anh sử dụng EHRSQL 2024 và mẫu đánh giá công khai của hệ thống M3 (PLOS Digital Health, 2026). Nghiên cứu đánh giá riêng tính đúng của truy vấn và câu trả lời cuối, đồng thời đối chiếu với đầu ra baseline M3 theo một rubric thống nhất. Kết quả trên mẫu demo được phân biệt với đánh giá trên MIMIC-IV Mini và hội thoại đa lượt.

## File đã chuẩn bị

- `datasets/m3-ehrsql-2024/answerable.inputs.jsonl`: 100 câu, chỉ ID và question.
- `datasets/m3-ehrsql-2024/unanswerable.inputs.jsonl`: 100 câu, chỉ ID và question.
- Hai file `.gold.jsonl` tương ứng: gold và published outputs/labels, tuyệt đối không đưa vào inference.
- `sources/ehrsql-m3-v1.0.5/mimic_iv.sqlite`: database lịch sử đã pin và kiểm tra.
- `m3_audit_manifest.json`: commits, SHA256, ánh xạ ID, kết quả preflight, khác biệt phiên bản và transcript audit.
- `audit_m3.py`: script offline tái lập kiểm tra.

Các source tải về nằm trong `research/sources/`, được ignore trong Git. Không sửa code hệ thống, không đổi database hiện có, không push hay chạy LLM. Không liên hệ tác giả hoặc gửi tài liệu cho người khác trong quá trình kiểm tra này.
