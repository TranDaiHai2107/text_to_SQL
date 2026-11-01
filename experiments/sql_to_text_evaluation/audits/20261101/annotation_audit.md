# Audit độc lập vòng hai — nhãn tiếng Anh

Ngày 01/11/2026. Trạng thái: passed_with_scope_limitations. Không API/model call.

Đã kiểm tra đủ 7454 câu, thực thi lại 6539 SQL chuẩn read-only; 7454 câu tiếng Anh khớp dữ kiện kết quả theo numeric3/toàn bộ dòng. Lỗi phát hiện: 0.

Không import builder, renderer hoặc các audit cũ. Kiểm tra độc lập SQL/result, grammar của text, CSV, input chỉ có câu hỏi, input riêng cho verbalizer, ID/split và hash nguồn/147 file đóng băng.

- train:5.124; validation:1.163; test:1.167. Không trùng ID giữa các split.
- Câu không thể trả lời:915; kết quả rỗng:1; SQL NULL:0.
- Query có dòng trùng:75; query trên100dòng:44; tối đa:152dòng.

## Giới hạn phải giữ trong kết luận

Các nhãn là tiếng Anh có kiểm soát chỉ nêu giá trị, chưa phải câu trả lời hội thoại được bác sĩ duyệt. Câu hỏi Yes/No có thể nhận giá trị0.0/1.0, mã bệnh nhân có thể được numeric3 chuyển thành số có đuôi.0. Điều này giữ quy ước chấm, nhưng chưa kiểm định độ tự nhiên hoặc ý nghĩa lâm sàng. Audit máy không chứng minh nhãn hoàn toàn chính xác về mặt ngữ nghĩa.

Full-result English giữ152dòng trong ví dụ top-k có DENSE_RANK đồng hạng, trong khi gold official chỉ100dòng. Đây là khác biệt phạm vi đã khai báo, không phải lỗi cần tự cắt dữ liệu.

Ví dụ và toàn bộ số liệu/hash nằm trong annotation_audit.json. Không sửa bất kỳ artifact gốc nào.
