# V4 — benchmark-aligned numeric agreement and ICD validation

V3 giữ nguyên tại [báo cáo V3](../ours_improved_v3/runs/deepseek_flash_v3_20261029_r2/FINAL_REPORT.md): RS10=71,21. V4 là vòng phát triển tiếp theo; không sửa lịch sử V3 và không gọi lại mô hình tác giả/Vanna.

## Hai thay đổi từ tuning

- So kết quả bằng `process_item` chính thức: số làm tròn3chữ số, nhưng **giữ toàn bộ dòng**, duplicate và số cột; không lấy cap100dòng của scorer làm bằng chứng đồng thuận. Các biểu thức thời lượng tương đương (`strftime('%J')`/`julianday`) có thể khác ở chữ số máy nhưng đúng cùng đáp án benchmark. Scorer/gold/DB chính thức **không thay đổi**.
- Kiểm tra bare ICD code với full dictionary191.562mã, không chỉ các mã đã xuất hiện ở patient facts. Giữ bản ghi/SQL nguồn bất biến; mã không có prefix dataset và không thuộc dictionary bị guard rõ ràng. Punctuation-colliding exact label là soft risk flag, không tự kết luận SQL sai.

Không đổi prompt/model/settings của generation V3. Chính sách có baseline raw strict3 và4nhánh round3, có/không gate trivial scalar hoặc exact binding. Chọn trên tuning với coverage≥35%; không cho phương án từ chối tất cả thắng. Độ chính xác3số là quy ước benchmark, không mặc định thích hợp với mọi chỉ số lâm sàng khác.

## Dữ liệu phát triển mới

Giữ300câu tuning, chọn **100câu audit mới**, không trùng các câu từng chấm ở calibration/audit V2/V3 hoặc rule evidence. Toàn bộ400câu mới và câu trùng nội dung bị loại khỏi RAG trong V4. Vì tập loại đổi, các prompt tuning có thể đổi; cache chỉ dùng lại khi hash toàn request giống hệt. Không tái sử dụng checkpoint tuning cũ một cách tùy tiện.

V4 có14kiểm tra mới đã qua, gồm full-row numeric fingerprint, dictionary universe, source immutability, raw-reference scoring và audit disjointness. Phần generation tái sử dụng V3 đã qua42kiểm tra trước đó.

## Test dùng lại generation đã khóa

Sau khi khóa policy và chấm100audit mới, V4 chạy validation/selection trên đầy đủ1.167bộSQL V3 đã sinh. **Không có model call mới trên test**; vẫn chạy SQL read-only và official scorer. Generation hiệu dụng phải tính cả chi phí V3 đã sinh các candidate, không gọi nó là inference miễn phí. So sánh V3/V4 giữ cùng model/candidates/budget generation để đo tác động gói validation+selection.

Đây vẫn là nghiên cứu exploratory: đã biết điểm test tổng thể V3 và các vòng trước, nên không gọi test này là holdout độc lập. Hai thay đổi V4 được tìm từ lỗi tuning; không đọc lỗi test từng câu để tạo guard hay chọn policy. Giữ tất cả phiên bản và báo cả kết quả không đạt mốc paper.

## Chạy

Dùng Python trong`.venv` từ root:

1. `experiments/ours_improved_v4/run_v4.py --run-name deepseek_flash_v4_20261029_r1 --phase tune --workers 8`
2. Giữ cùng run-name, đổi phase thành `audit`.
3. Sau audit, phase `test` chỉ replay SQL cache V3 với policy đã khóa.
4. `experiments/ours_improved_v4/report_v4.py --run-name deepseek_flash_v4_20261029_r1 --docker` chấm cùng DockerSQLite/official scorer và tạo báo cáo.

API key đọc từ`.env`, không truyền quaCLI. Không tự nạp credit hoặc chuyển model. Folder runs giữ protocol, source hashes, chính sách, cache nguồn, checkpoint và kết quả.

Mốc [ProbGate paper](https://aclanthology.org/2024.clinicalnlp-1.65/) RS10=74,21 là điểm công bố đã replay cache. EX77,73% là số tính thêm từ cache, không phải số EX công bố. Khác model/fine-tuning và có thêm dev làm knowledge, nên điểm cao hơn cũng chưa tự chứng minh phương pháp tốt hơn trong một đối chứng hoàn toàn đồng điều kiện.
