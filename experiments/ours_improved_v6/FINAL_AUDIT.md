# Final audit V6 — 01/11/2026

Trạng thái: fully_verified. Không API/model call, không chỉnh phương pháp.

Policy/protocol/code và reference manifest khớp lock;147 file gốc và database nguyên vẹn.
Fresh SQLite read-only + normalizer/scorer độc lập khớp toàn bộ2×1.167 kết quả chấm SQL; V5 khớp lịch sử.
109 test và5 subtest đạt (114caseJUnit).

- V5_frozen: RS10=74.89288775; EX=92.29122056%; VSR=75.66409597%; wrong=21.
- V6_dev_selected: RS10=74.97857755; EX=92.39828694%; VSR=75.74978578%; wrong=21.

Transitions V5→V6: {"correct -> correct": 1084, "abstained_answerable -> abstained_answerable": 61, "wrong -> wrong": 21, "abstained_answerable -> correct": 1}.

- English V5_frozen:1167/1167 output đã đối chiếu trực tiếp với kết quả SQL prediction; fact-EM độc lập=92.88774636%; không thay bằng goldSQL.
- English V6_dev_selected:1167/1167 output đã đối chiếu trực tiếp với kết quả SQL prediction; fact-EM độc lập=92.97343616%; không thay bằng goldSQL.

English là renderer theo mẫu, không phải LLM sinh tự do hoặc gold được chuyên gia duyệt. Full-result English không cap100, khác quy ước officialSQL; không so như cùng metric. Lexical replay dùng scorer đã khóa, còn SQL scoring và English fact parsing/thực thi trong audit này là độc lập.
