# Tổng hợp audit độc lập — 01/11/2026

Ba agent kiểm tra riêng số liệu Text-to-SQL, toàn bộ nhãn tiếng Anh và bộ chấm. Không gọi API hoặc model; 147 file đã chốt giữ nguyên.

## Kết quả xác nhận

- So sánh: replay độc lập 4 × 1.167 prediction, khớp từng kết quả chấm cũ; RS/EX/VSR, các số đếm và mẫu số không sai. RS10 vẫn là V5: 74,89; Vanna: −58,10; Vanna+GEF: −12,08; ProbGate: 74,21.
- Nhãn: thực thi lại 6.539 SQL chuẩn; 7.454/7.454 output tiếng Anh khớp toàn bộ dữ kiện theo numeric3; 0 lỗi, 0 timeout. CSV/JSONL, membership các split, input sạch và input verbalizer đều đúng. Không đổi nhãn.
- Bộ chấm: 27 kiểm tra audit độc lập đạt, gồm đối chiếu DP trên 961 cặp chuỗi. Sau sửa có 61 test và 5 subtest đạt (66 case theo JUnit); self-check scorer toàn bộ ba split đạt, không phải điểm mô hình.

## Hai lỗi đã tìm và sửa

1. **P2 — JSON trùng ID/key bị ghi đè âm thầm.** Loader mới từ chối key trùng trong cả JSON và JSONL trước khi mất bản ghi ban đầu. Có test hồi quy và agent kiểm tra lại.
2. **P2 — reference text có thể mâu thuẫn result_rows.** Chế độ controlled giờ parse gold English và yêu cầu khớp dữ kiện/trạng thái trước khi chấm prediction. Reference mâu thuẫn dừng chấm. Có test hồi quy và agent kiểm tra lại.

Hai lỗi nằm ở việc tiếp nhận đầu vào mới của scorer. Nhãn hiện tại không có các mâu thuẫn này; kết quả Text-to-SQL đã báo cáo không bị ảnh hưởng. Các lỗi trước sửa được ghi nhận bằng probe tương tác; các lần chạy script audit lưu trong metric_audit.json đều diễn ra sau sửa. Không gắn nhãn nhầm các script sau sửa là bằng chứng thực thi trước sửa.

## Giới hạn vẫn phải giữ

- Nhãn mới là tiếng Anh có kiểm soát nêu giá trị/kết quả SQL, chưa phải đáp án hội thoại được bác sĩ thẩm định. Câu hỏi Yes/No có thể nhận 0.0/1.0; không suy diễn thêm ý nghĩa lâm sàng.
- Fact-EM đòi đúng grammar canonical, cả cách viết số và sắp dòng; không tự xác nhận mọi paraphrase tiếng Anh.
- 44 câu giữ đủ hơn 100 dòng (tối đa 152), trong khi official SQL scorer giới hạn 100 dòng. Không so hai điểm như cùng tác vụ.
- Chưa đánh giá sinh tiếng Anh thực tế của V5/Vanna; chưa có kết quả SQL→text của paper để đối chiếu phần này.
- RS10 V5 nhỉnh hơn paper quan sát chưa chứng minh ưu thế nghiên cứu độc lập.

Chi tiết: [so sánh](comparison_audit.md), [nhãn](annotation_audit.md), [metric](metric_audit.md). Số liệu/hash máy đọc: AUDIT_SUMMARY.json.
