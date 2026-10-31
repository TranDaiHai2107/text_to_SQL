# Xác nhận kết quả hiện tại — EHRSQL 2024

Đã thực thi lại prediction của cả bốn nhánh trên cùng 1.167 câu test, 934 answerable và 233 unanswerable, cùng SQLite database và official scorer. Từng nhãn chấm của cả bốn nhánh khớp kết quả đã lưu. Không gọi lại model/API, không sửa V5 hoặc gold.

## Kết quả đã xác nhận

- **V5**: RS0=92.89; RS5=83.89; RS10=74.89; RSN=-2007.11; EX=92.29%; VSR=75.66%; sai=21.
- **Vanna**: RS0=85.00; RS5=13.45; RS10=-58.10; RSN=-16615.00; EX=85.87%; VSR=82.86%; sai=167.
- **Vanna_GEF**: RS0=86.46; RS5=37.19; RS10=-12.08; RSN=-11413.54; EX=85.87%; VSR=78.58%; sai=115.
- **ProbGate_paper_cache**: RS0=81.92; RS5=78.06; RS10=74.21; RSN=-818.08; EX=77.73%; VSR=62.98%; sai=9.

RS là metric paper. EX tính trên 934 câu answerable; VSR tính SQL thực thi thành công trên toàn bộ 1.167 câu. EX/VSR của paper được tính bổ sung từ prediction tác giả phát hành, không phải hai cột công bố trong paper.

Paper là replay prediction tác giả, chưa chạy lại model tác giả. Vanna là cấu hình legacy SQL/RAG trong Vanna 2.0.2, dùng DeepSeek Flash và train+dev làm knowledge. V5 cũng dùng DeepSeek Flash, nhưng có ba nhánh generation/selection nên chưa phải đối chứng cùng ngân sách.

## Kết luận đúng phạm vi

Có thể xác nhận các số trên là kết quả đo được của cấu hình hiện tại. V5 nhỉnh hơn ProbGate về RS10 quan sát và cao hơn Vanna trong cấu hình đã chạy. Paper vẫn ít câu trả lời sai hơn và có RSN tốt hơn. Chưa chứng minh ưu thế phương pháp hay tổng quát hóa độc lập.

V5 giữ nguyên làm bản chốt. Mở rộng database/dữ liệu, chuyển ngữ và xác nhận độc lập để bước tiếp theo theo yêu cầu của người dùng. Kết quả này chỉ English→SQL, không đánh giá ASR hoặc SQL→text.

Lần kiểm tra này chạy official scorer trên host. Docker daemon hiện chưa chạy nên không gán nhãn fresh Docker verified cho cả bốn nhánh; V5/paper có đối soát Docker từ vòng trước và kết quả fresh host khớp từng câu.

[Paper ProbGate](https://aclanthology.org/2024.clinicalnlp-1.65/). Chi tiết hash/provenance: `CONFIRMED_RESULTS.json`.
