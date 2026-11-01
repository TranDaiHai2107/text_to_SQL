# Kết quả cuối Text-to-SQL — đối chiếu ngày 01/11/2026

Đã thực thi lại prediction đã lưu trên toàn bộ 1.167 câu test EHRSQL 2024 (934 answerable, 233 unanswerable). Từng kết quả chấm khớp kết quả cũ; 147 file đóng băng không đổi. Không gọi API, không chạy lại model, không sửa gold hoặc bộ chấm Text-to-SQL.

- **V5**: RS0 **92.89**, RS5 **83.89**, RS10 **74.89**, RSN **-2007.11**; EX **92.29%**, VSR **75.66%**.
  Đúng SQL: 862; từ chối đúng: 222; trả lời sai: 21; từ chối nhầm câu có đáp án: 62; lỗi thực thi: 0. Precision trên các câu đã trả lời: 97.62%.
- **Vanna**: RS0 **85.00**, RS5 **13.45**, RS10 **-58.10**, RSN **-16615.00**; EX **85.87%**, VSR **82.86%**.
  Đúng SQL: 802; từ chối đúng: 190; trả lời sai: 167; từ chối nhầm câu có đáp án: 8; lỗi thực thi: 2. Precision trên các câu đã trả lời: 82.77%.
- **Vanna_GEF**: RS0 **86.46**, RS5 **37.19**, RS10 **-12.08**, RSN **-11413.54**; EX **85.87%**, VSR **78.58%**.
  Đúng SQL: 802; từ chối đúng: 207; trả lời sai: 115; từ chối nhầm câu có đáp án: 43; lỗi thực thi: 0. Precision trên các câu đã trả lời: 87.46%.
- **ProbGate_paper_cache**: RS0 **81.92**, RS5 **78.06**, RS10 **74.21**, RSN **-818.08**; EX **77.73%**, VSR **62.98%**.
  Đúng SQL: 726; từ chối đúng: 230; trả lời sai: 9; từ chối nhầm câu có đáp án: 202; lỗi thực thi: 0. Precision trên các câu đã trả lời: 98.78%.

## Đọc các chỉ số

- RS(c) = 100 × (số đúng − c × số trả lời sai) / 1.167. Số đúng gồm SQL đúng và từ chối đúng; từ chối nhầm nhận 0. RSN dùng c=1.167.
- EX chỉ có mẫu số 934 câu có đáp án. VSR có mẫu số toàn bộ 1.167 câu và đo khả năng thực thi SQL, không đo nội dung đúng.
- Vanna_GEF là cùng lần sinh của Vanna có thêm bộ lọc thực thi/kết quả rỗng; không phải lần chạy một model khác.

## Nguồn và giới hạn so sánh

[ProbGate at EHRSQL 2024: Enhancing SQL Query Generation Accuracy through Probabilistic Threshold Filtering and Error Handling](https://aclanthology.org/2024.clinicalnlp-1.65/) công bố các điểm RS. EX và VSR ở đây được tính thêm từ prediction tác giả phát hành, không phải hai cột công bố trong bài báo. Đây là replay prediction tác giả, chưa tái huấn luyện/chạy lại model tác giả.

V5 và Vanna đều dùng DeepSeek Flash, nhưng V5 có ba nhánh sinh/chọn SQL nên ngân sách inference chưa bằng nhau. Bài báo dùng model và quy trình fine-tune khác. V5 dùng train+dev làm knowledge; test đã được quan sát trong quá trình phát triển nhiều phiên bản.

V5 nhỉnh hơn paper **0.6855 điểm RS10 quan sát**, và hơn Vanna trong cấu hình đã chạy. Paper vẫn ít câu sai hơn (9 so với 21) và RSN tốt hơn. Chênh lệch này **chưa chứng minh ưu thế nghiên cứu độc lập**; khoảng tin cậy paired-bootstrap đã lưu của RS10 [-9,08; 10,20] chứa 0.

Kết quả này chỉ đánh giá English→SQL. Phần tham chiếu và metric English→English mới phải được báo cáo riêng; không gán điểm SQL→text cho paper khi paper không công bố phần đó.

Chi tiết nguồn, hash, mẫu số và công thức nằm trong `TEXT_TO_SQL_COMPARISON.json`. Lần kiểm tra này chạy SQLite trên host, không gắn nhãn fresh Docker verification.
