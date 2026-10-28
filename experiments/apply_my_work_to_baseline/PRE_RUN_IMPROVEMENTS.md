# Cải tiến trước khi đánh giá — 24/10/2026

## Mục tiêu và phạm vi

Cải thiện độ vững của pipeline English → SQL trên EHRSQL, không fine-tune và không gọi API. Chưa có bằng chứng về mức tăng EX/RS10. Không dùng kết quả cũ của tác giả làm đầu ra của hệ thống mình. Bước SQL → câu trả lời tiếng Anh không được các metric SQL ở đây đánh giá.

## Các thay đổi

1. **Giữ đủ schema trong ứng viên mặc định.** Database benchmark chỉ có 17 bảng. `full_schema` lấy từ điển và ví dụ train nhưng không cắt bảng. Mục đích là loại bỏ lỗi mất thông tin do schema retrieval. Schema pruning cũ vẫn có để so sánh trên dev. Đánh đổi: prompt có thể dài hơn; chưa biết phương án nào đạt điểm cao hơn.
2. **Đối chứng cùng bộ lọc.** Thêm `base_gef` và `examples_gef`, dùng lại SQL tương ứng. So nhánh đề xuất có GEF với base có GEF để không quy toàn bộ mức tăng cho RAG. GEF không gọi LLM. Đây chưa phải ProbGate đầy đủ: chưa có logprob gate cho các prediction mới.
3. **Sửa SQL với schema đầy đủ khi nhánh pruning bị lỗi.** Trong tối đa hai lượt sửa hiện có, bổ sung DDL thật còn thiếu trước khi yêu cầu sửa. Không cung cấp gold, SQL tham chiếu hay hàng kết quả bệnh nhân. Không sửa mù một câu `null` hợp lệ.
4. **Rewrite thành nhánh tùy chọn.** Mặc định không gọi rewrite cho câu hỏi độc lập. Nếu bật, guard bảo toàn thứ tự và số lượng các giá trị số, từ phủ định, quan hệ thời gian, lượng từ, phép so sánh và tên nằm trong dấu nháy. Nếu thay đổi, giữ nguyên câu hỏi. Kiểm tra từ vựng không chứng minh tương đương ngữ nghĩa hoàn toàn.
5. **Giữ lỗi generation trong cách chấm.** Response bị cắt token được đánh dấu lỗi, kể cả phần đã sinh là `null` hay SQL thực thi được. Export prediction dùng chuỗi SQL không hợp lệ cho trường hợp này để Docker cũng chấm lỗi. Chỉ nhánh GEF mới chủ động chuyển lỗi thành `null`; tách rõ với model tự từ chối.
6. **Đo tính đáng tin và tài nguyên theo từng nhánh.** Báo đúng SQL, sai SQL, từ chối nhầm câu answerable, trả lời sai câu unanswerable, coverage và precision. Có tổng token/call theo hash của mỗi cấu hình, kèm số record usage thiếu. Các nhánh chia sẻ call nên không cộng tổng từng nhánh để tính hóa đơn thực tế.
7. **Đóng băng ứng viên trước test.** CLI bắt buộc chỉ định primary variant khi chạy test. Không tự chọn nhánh có test score đẹp nhất. Code/config thay đổi phải dùng run name mới.

## Bộ đối chứng mặc định trên dev

- `base`: cùng system prompt và toàn bộ schema, không retrieval ví dụ/từ điển, không sửa lỗi.
- `base_gef`: dùng lại base rồi lọc lỗi/kết quả rỗng.
- `examples`: toàn bộ schema + bốn ví dụ train được truy xuất.
- `examples_gef`: dùng lại examples rồi lọc.
- `full_schema_rag`: toàn bộ schema + ví dụ train + từ điển y khoa.
- `full_schema_rag_agentic`: nhánh trên, thêm sửa lỗi thực thi tối đa hai lần.
- `full_schema_rag_agentic_gef`: nhánh sửa lỗi, thêm lọc.

Nếu ba generation ban đầu đều hợp lệ, bảy nhánh dùng **ba lượt sinh SQL**, không cần bảy lượt và không gọi rewrite. Nếu SQL lỗi, nhánh agentic có thể phát sinh tối đa hai lượt sửa nữa. Số token vẫn phụ thuộc độ dài schema/context/output. Ứng viên primary trên dev là nhánh cuối; chọn lại dựa trên dev nếu cần rồi đóng băng trước test.

## Giới hạn vẫn còn

- Chưa có bộ lọc độ tin cậy phát hiện SQL chạy được nhưng trả lời sai. API/model phải hỗ trợ logprobs thích hợp nếu muốn áp dụng ProbGate; ngưỡng chọn trên dev.
- Sửa lỗi thực thi không kiểm tra đầy đủ ý nghĩa lâm sàng, thời gian hoặc phép tổng hợp. Chưa thêm lượt semantic verifier vì chưa có bằng chứng nó cải thiện và nó làm tăng chi phí.
- Model của tác giả đã fine-tune. So cùng model không fine-tune chỉ là so với ProbGate điều chỉnh, không phải tái hiện nguyên bản.
- Chưa tích hợp provider mới. Không thể chỉ thay tên Gemini/DeepSeek/GPT vào Groq rồi chạy.
- Chưa chạy benchmark hay suy ra xác suất vượt bài báo từ unit tests. Vẫn cần pilot dev có đo token và phân tích lỗi trước full dev/test.

## Kiểm chứng cục bộ

`tests/test_pipeline.py` có 12 test, gồm SQL chỉ đọc, guard rewrite, phục hồi schema khi sửa, chia sẻ call giữa nhánh, response cắt token, lỗi quota không thành null và phân rã điểm trên fixture tổng hợp. Không dùng fixture tổng hợp như kết quả benchmark.

Đã chạy thêm 13 test baseline và parser PowerShell, đều đạt. Smoke test offline trên index thật với hai câu hỏi tự đặt: mỗi prompt có đủ 17 bảng, bốn ví dụ đều thuộc train, năm ứng viên từ điển; không gọi API. Prompt dài 8.826 và 8.629 ký tự (không phải số token). Các count index vẫn là 6.417 / 17 / 5.124. Xem `PRE_RUN_CHECKS.json`.

Không thay schema, gold, cache tác giả hay runtime chấm official. Các file generation/evaluation mới được lưu hash cho lần chạy tiếp theo.
