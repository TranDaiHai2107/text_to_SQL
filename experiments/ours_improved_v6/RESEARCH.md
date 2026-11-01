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
