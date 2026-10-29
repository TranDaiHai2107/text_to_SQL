# Hệ thống đề xuất v2 — cải thiện rồi chạy lại riêng hệ thống của mình

Đây là thí nghiệm English → SQLite trên EHRSQL 2024, tách khỏi hệ thống ứng dụng và các lần chạy cũ. Không fine-tune; không gọi lại mô hình của tác giả hoặc Vanna.

## Kết quả đã hoàn tất

Đủ 1.167/1.167 câu test; official scorer trong Docker khớp từng câu với host. Xem [báo cáo đầy đủ](runs/deepseek_flash_v2b_20261028/FINAL_REPORT.md) và [kết quả JSON](runs/deepseek_flash_v2b_20261028/FINAL_RESULTS.json).

- Nhánh generation mới: EX **91,86%**, RS10 **5,91**. V1 trước đó: EX **88,12%**, RS10 **−49,10**; cùng DeepSeek Flash và knowledge train+dev.
- Nhánh đầy đủ/primary đã khóa: EX **77,94%**, RS10 **0,00**. Review/sửa ngữ nghĩa gây hại trong lần chạy này, dù giúp giảm trả lời trên câu unanswerable. Không đổi primary sau khi xem test.
- Mốc tốt nhất trong paper: RS10 **74,21**. Chưa vượt paper theo metric này. EX paper tính thêm từ cache là **77,73%**, không phải EX công bố.
- Gate logprob bị vô hiệu vì tín hiệu calibration toàn 0. Không coi phương án từ chối toàn bộ là cải thiện.

13 kiểm tra tự động đã qua. Nhánh generation là ứng viên để xác nhận trên holdout mới; kết quả hiện tại mang tính khám phá vì thiết kế đã tham khảo lỗi test của v1. Giữ cả các bước không hiệu quả trong báo cáo để tránh chỉ chọn kết quả đẹp.

## Thay đổi

- RAG vẫn có schema, từ điển y khoa và ví dụ Q/SQL. Ví dụ được xếp hạng kết hợp BM25 và embedding bằng reciprocal rank fusion; bỏ ảnh hưởng của mã bệnh nhân trong tìm kiếm từ khóa. Các ví dụ dùng vai trò user/assistant riêng để tránh sao chép câu cuối trong prompt.
- Từ điển bổ sung `d_items.abbreviation`, `linksto` và các giá trị specimen/test/organism từ microbiology. Không đưa kết quả truy vấn của bệnh nhân vào LLM.
- Guard kiểm tra SQL, mã bệnh nhân tự thêm, LIMIT ở đầu truy vấn và giá trị từ điển không tồn tại. Một lượt sửa giới hạn khi có vấn đề.
- LLM kiểm tra lại sự phù hợp giữa câu hỏi và SQL: nội dung trả lời, clinical concept, bộ lọc, thời gian, tổng hợp. Tối đa một lượt sửa ngữ nghĩa và một lần kiểm tra lại. Kiểm tra này có thể sai; không thay thế chuyên gia y khoa.
- Lấy logprob thực từ câu SQL sau lần sửa cuối, trung bình 10 token thấp nhất sau khi bỏ reserved words như cách ProbGate. Kết hợp với logprob của token `true` trong review nếu có. Đây là điểm heuristic cần calibration, không phải xác suất đúng.
- Gate có thể từ chối SQL không đủ tin cậy. Trước khi dùng, kiểm tra điểm có hữu hạn và có biến thiên: tín hiệu thiếu hoặc hằng số sẽ vô hiệu gate, giữ các bước kiểm tra ngữ nghĩa/thực thi. Nếu hợp lệ, ngưỡng chọn theo RS10 trên 200 câu dev; 100 câu dev khác dùng audit, không chọn lại ngưỡng. Mỗi câu dev bị loại chính ID và các câu trùng nguyên văn khỏi RAG. Knowledge base cuối vẫn gồm toàn bộ train + dev: 6.287 câu.

Không gọi rewrite thêm cho câu benchmark đơn lẻ không có lịch sử, tránh tự đổi nghĩa câu hỏi. Prompt buộc giữ nguyên ý, thực thể và điều kiện.

## Quy trình cố định trước khi chạy

`protocol.json` lưu hash nguồn, dữ liệu, lưới ngưỡng và 300 ID dev đã chọn bằng hash có phân tầng. `threshold.json` lưu toàn bộ điểm calibration và ngưỡng đã khóa trước khi chạy test 1.167 câu. Ba cấu hình dùng chung các lần gọi: `v2_grounded`, `v2_verified`, `v2_calibrated` (primary, RS10). Không chọn cấu hình thắng bằng test.

Code inference không đọc gold test. Scorer đọc gold sau khi inference đã kết thúc, dùng nguyên chuẩn EHRSQL: chuẩn hóa số 3 chữ số, thứ tự dòng, RS0/RS5/RS10/RSN. EX trên 934 câu answerable; VSR là tỷ lệ SQL thực thi được trên toàn bộ 1.167 câu.

**Giới hạn nghiên cứu:** v2 được thiết kế sau khi đã xem lỗi test của v1, nên kết quả mới là cải thiện khám phá có tham khảo test, không phải holdout độc lập. Calibration là leave-one-question-out trong dev, không phải một tập dữ liệu hoàn toàn ngoài knowledge corpus. Muốn kết luận tổng quát mạnh cần dữ liệu chưa từng dùng để thiết kế hoặc protocol cross-validation được khóa trước.

### Sửa lỗi calibration trước khi chấm test

Lần khởi chạy `deepseek_flash_v2_20261028` phát hiện cả 57.894 token calibration đều có logprob bằng 0.0 tại temperature=0; 217 câu được chấp nhận có điểm tin cậy giống nhau. Lưới ngưỡng suy biến thành giữ tất cả hoặc từ chối tất cả. Không thể diễn giải đó là bộ lọc rủi ro hữu ích. Không suy rộng phát hiện này sang mọi cấu hình/model DeepSeek.

Đã dừng lần khởi chạy này khi có 353 checkpoint test, **trước chấm gold test**. Bản sửa bổ sung kiểm tra tín hiệu hằng số và tự vô hiệu gate, không dựa trên điểm test. Lần tiếp tục `deepseek_flash_v2b_20261028` kế thừa cache API/calibration, tái tạo record test bằng cùng generation/review và chạy hết phần còn lại. Không trả phí lại cho request đã có cache. `resume_provenance.json` lưu nguồn; `source_snapshot/` ở lần cũ giữ mã trước bản sửa. Primary vẫn là pipeline có calibration, nhưng logprob gate của cấu hình này bị tắt; không tuyên bố đã tái hiện ProbGate thành công trên DeepSeek. Xem [API reference chính thức](https://api-docs.deepseek.com/api/create-chat-completion/) về trường logprob; kết luận toàn 0 ở đây đến từ cache thực nghiệm.

## Kết quả tác giả dùng để tham chiếu

Paper: [ProbGate at EHRSQL 2024: Enhancing SQL Query Generation Accuracy through Probabilistic Threshold Filtering and Error Handling](https://aclanthology.org/2024.clinicalnlp-1.65/), [mã tác giả](https://github.com/venzino-han/probgate_ehrsql).

RS0 **81,92**, RS5 **78,06**, RS10 **74,21**, RSN **−818,08** là số công bố trong paper, đã được đối chiếu bằng prediction cache phát hành. **EX 77,73% là số tính thêm từ cache**, không phải cột EX paper công bố. Chưa tái huấn luyện hoặc gọi lại model fine-tuned GPT-3.5 của tác giả. DeepSeek Flash + knowledge train/dev khác backbone và protocol của paper, nên đây là đối chiếu hệ thống, không đủ tách hiệu quả riêng của phương pháp.

## Chạy

Từ thư mục gốc dự án, dùng Python trong `.venv` chạy `experiments/ours_improved_v2/run.py`. Key đọc từ `.env`, không truyền qua dòng lệnh. Có checkpoint từng câu, cache request, log token, trạng thái hạn mức và khóa cấu hình để tiếp tục đúng lần chạy. Lỗi API/quota dừng có checkpoint; không tự biến câu chưa chạy thành `null`.

Giữ nguyên các kết quả v1 và Vanna để đối chiếu. Thư mục `runs/` chứa dữ liệu sinh ra và không đưa vào Git.
