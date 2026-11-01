# Review code V6 trước khi chấm test — 01/11/2026

**Kết quả:** hai lỗi projection đã được sửa và kiểm tra lại; không còn blocker tái hiện được trong phạm vi review code và fixture tổng hợp. Không đọc câu hỏi, prediction hoặc gold test của benchmark; không gọi API/model; reviewer không chỉnh code production.

Đã đọc `run_v6.py`, `postprocess_v6.py`, `english_evaluation.py` cùng các helper được kế thừa. Hash ba module sau sửa và kết quả **12 kiểm tra runtime trên fixture tổng hợp** nằm trong `review.json`.

## Hai lỗi đã chặn trước khi khóa test

1. **R1 / P1 — ORDER BY theo vị trí bị đổi nghĩa khi xóa cột SELECT.** Fixture có tháng1 giá trị100 và tháng2 giá trị1: query lấy tháng và AVG, `ORDER BY 1 LIMIT 1`, ban đầu chọn tháng1/100. Khi xóa projection tháng, ordinal1 trỏ vào AVG và chọn1. Bản sửa bỏ qua projection repair khi ORDER có numeric literal; reviewer kiểm tra lại query này không còn bị sửa.
2. **R2 / P2 — câu hỏi yêu cầu rõ period key vẫn mất cột period.** Câu `Show the monthly average cost by month.` trước sửa vẫn bị xóa projection tháng. Guard mới nhận `by`, `per`, `for each` với period; ba cách viết tương ứng đều được kiểm tra độc lập và giữ nguyên. Trường hợp monthly average không yêu cầu period label vẫn còn được sửa.

Các probe trước sửa được quan sát tương tác, trước khi reviewer ghi hash snapshot chính thức; không mô tả chúng như một lần chạy script trên bản code cũ đã lưu. Các hash/runtime check trong `review.json` là của bản **sau sửa**.

## Tính bất biến, policy và provenance

- Enhancement deep-copy ứng viên, giữ record nguồn và bằng chứng repair. Trường hợp không thay đổi hoặc proposal lỗi/rỗng giữ prediction V5.
- `v5_reference` chọn từ danh sách ứng viên gốc. Các sửa literal không tạo thêm phiếu model hoặc request mới.
- Fixture kiểm tra hai record trùng request hash không được tính thành hai phiếu. Pair fallback có điều kiện plan từ chối một cặp chỉ gồm direct/structural. Selection không mutate candidate đầu vào.
- Runner khai báo grid trước, chọn bằng RS10 của tune300. Audit100 lịch sử được ghi đúng là development diagnostic đã tiếp xúc; không gọi là validation độc lập.
- Policy, code và manifest reference tiếng Anh được khóa trước test. Prediction SQL được lưu trước khi đọc gold test. Marker `TEST_COMPLETE.json` chặn chạy lại test đã hoàn tất trong cùng run.
- Đây là reuse generation cache DeepSeek nguồn, không phải một vòng gọi lại model. Báo cáo ghi incremental API bằng0 và vẫn thừa nhận compute generation nguồn.

Theo cập nhật từ parent sau vòng dev đã khóa: policy được chọn là **v6_strict3**; các phương án pair fallback không được áp dụng lên test. Reviewer không đọc dữ liệu hoặc kết quả test để đưa ra đánh giá này.

## Giới hạn ngữ nghĩa của ba rule

**Casefold ICD** có bằng chứng ánh xạ vật lý duy nhất trong đúng dictionary. Điều đó không chứng minh phần grouping, thời gian hoặc aggregate còn lại của SQL đúng.

**Period projection** vẫn là heuristic về output contract của benchmark. Hai guard mới tránh lỗi rõ ràng; việc nhận diện mọi cách diễn đạt tiếng Anh chưa được chứng minh.

**Organism IS NOT NULL** là quy ước EHRSQL dựa trên train, không phải định lý metadata. Fixture cho thấy nếu test đầu tiên có NULL organism và test sau có X, thêm điều kiện non-null sẽ chuyển từ test đầu sang test đầu có organism. `DEV_FINDINGS.md` báo 84/84 train SQL tương ứng dùng non-null; reviewer code-only không đọc nhãn để đếm lại. Rule có flag riêng, loại negative/missing/null wording và cần được báo đúng như một benchmark-convention adaptation. Không mô tả là bảo toàn ngữ nghĩa lâm sàng phổ quát.

## Phần English → SQL → English

Luồng end-to-end dùng input sạch và **SQL prediction** rồi chạy database read-only, tạo/lưu câu tiếng Anh trước khi đọc reference. Execution failure có câu lỗi riêng, không trở thành từ chối đúng. Oracle gold-SQL được tách mode và ghi rõ không phải điểm hệ thống.

Output là renderer có kiểm soát, không phải LLM sinh văn bản tự do. Fact-EM so toàn bộ numeric3 result không cap100; nó không phải metric SQL chính thức hoặc đánh giá câu trả lời lâm sàng. Nên chạy English evaluation bằng `--sql-timeout 120` để khớp timeout SQL scorer; default30 có thể gây khác biệt vận hành khi máy bận.

Review này xác nhận tính hợp lý của code trong phạm vi đã kiểm tra, không cam kết V6 tăng điểm test hoặc chứng minh khả năng tổng quát hóa.
