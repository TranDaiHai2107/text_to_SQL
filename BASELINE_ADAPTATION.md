# Nhật ký thích nghi baseline

Không diễn giải code khung là reproduction đã xác nhận. Ghi commit nguồn, thay đổi, lý do, ảnh hưởng thuật toán và phép kiểm chứng trước khi chạy từng baseline.

| Baseline | Trạng thái | Thay đổi đã thực hiện | Lý do | Ảnh hưởng/kiểm chứng |
| --- | --- | --- | --- | --- |
| CLINSQL CoT | Khung offline | Interface model/BigQuery và prompt cấu trúc riêng | Tích hợp protocol chung | Chưa đối chiếu byte-for-byte với source; chưa chạy model/DB |
| MAC-SQL | Chưa tích hợp | Không | Chờ pipeline và chi phí | Không có kết quả |
| SDE-SQL | Chưa tích hợp | Không | Chờ quyền probe evidence | Không có kết quả; giới hạn dữ liệu có thể là blocker |

Nguồn: https://github.com/Barryshen1/ClinSQL, https://github.com/wbbeyourself/MAC-SQL, https://github.com/Lancelot-Xie/SDE-SQL.
