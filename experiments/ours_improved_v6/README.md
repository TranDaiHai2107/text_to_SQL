# V6 — hệ thống hiện tại

Cập nhật cấu trúc 08/11/2026. Bản hiện tại dùng DeepSeek Flash, policy `v6_strict3`.

- Text-to-SQL: RS10 **74,98**; EX **92,40%**; VSR **75,75%**, 1.167 câu test.
- English→SQL→English theo mẫu: fact-EM **92,97%**; WER **14,29%**.
- Paper đối chiếu: `baselines/probgate_ehrsql_2024`, ProbGate / ClinicalNLP 2024.
- [Báo cáo đầy đủ](runs/reviewed_20261101_once/FINAL_REPORT_VI.md); [JSON](runs/reviewed_20261101_once/FINAL_RESULTS.json).

## Sử dụng

Tại project root:

```powershell
python experiments/ours_improved_v6/current.py
python experiments/ours_improved_v6/current.py --verify-sql
```

Lệnh thứ hai thực thi lại prediction V6 đã lưu, đối chiếu từng kết quả official, không gọi API. `english_evaluation.py` vẫn nhận SQL prediction để chấm thêm đầu ra tiếng Anh.

## Kiến trúc

Hybrid retrieval/schema/dictionary/examples → ba nhánh direct/structural/plan → kiểm tra read-only và guard → compiler metadata/AST → đồng thuận strict 3/3 → SQL hoặc null. Renderer tiếng Anh theo mẫu nằm ở `../sql_to_text_evaluation/`.

## Lịch sử và tái lập

Code chạy V6 nằm trong `runtime/`: selection, normalization, namespace và sql_runtime. Không import module V1–V5 hoặc Groq. Cache đầu vào lịch sử vẫn nằm trong `_archive/20261106/workspace/experiments`; đây là dữ liệu, không phải code chạy. Code cũ đã xóa khỏi các folder đó, giữ bản nén `_archive/locked_source_evidence.zip` để kiểm tra 147 hash nguồn gốc. Không xóa cache/lock/kết quả so sánh.

Các run, protocol và báo cáo audit trước 06/11 giữ nguyên nội dung/hash lịch sử; code hiện tại đã đổi đường dẫn nên không giả mạo rằng hash code mới bằng lock cũ. Dùng `current.py --verify-sql` để xác nhận kết quả sau di chuyển. Các script fit/research lịch sử đã loại khỏi folder code. Thay đổi hash code bảo trì không phải một lượt chạy model mới.

M3 đã được loại khỏi nghiên cứu đang dùng. V6 là bản hiện tại nhưng exposure test lịch sử vẫn phải khai báo; việc dọn folder không tạo holdout độc lập.
