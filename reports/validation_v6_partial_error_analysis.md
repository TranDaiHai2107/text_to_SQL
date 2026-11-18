# Validation v6: kết quả một phần và phân tích lỗi của Ours

Ngày: 17/11/2026. Root: `results/restricted/validation_v6_503b7c46d4b79ffd`.
Model: gpt-5-mini-2025-08-07, reasoning medium cho cả 3 phương pháp.
Judge: gpt-5-mini *adapted* (không phải judge official Azure gpt-5-chat). Test 443 vẫn niêm phong.

## Trạng thái lần chạy

- Lần chạy dừng ở **119/190 câu ghép cặp đủ 3 phương pháp**, vì SDE-SQL chạm trần con $15. Trần này là mức phân bổ nội bộ, không phải trần tổng.
- Tổng đã chi ≈ **$39,05 / $60**:
  - lần 1: $4,03;
  - Ours: $13,10;
  - SDE-SQL: $12,45;
  - CoT: $1,51;
  - judge: $7,96.

  Các lượt gọi còn treo được tính ở mức trần đặt trước.
- BigQuery ≈ 4,7 TB / 14 TiB.

## Kết quả (119 câu)

| Phương pháp | SQL Score (adapted) | EX strict | Thực thi được | LLM calls/câu | Độ trễ TB* | $/câu |
|---|---|---|---|---|---|---|
| CLINSQL CoT | **0,348** | 2 | 113 | 1,5 | 65 s | 0,013 |
| SDE-SQL | 0,248 | **11** | 106 | 5,7 | 462 s | 0,094 |
| Ours v6 | 0,341 | 9 | 84 | 7,0 | 247 s | 0,078 |

\* Đo khi chạy 8 worker song song.

Chia theo độ khó (SQL Score):

| Độ khó | CoT | SDE | Ours |
|---|---|---|---|
| easy | 0,466 | 0,364 | 0,363 |
| medium | 0,316 | 0,230 | 0,338 |
| hard | 0,261 | 0,146 | 0,320 |

So sánh ghép cặp:
- Ours với CoT: SQL Score chênh −0,005, CI95 [−0,051; 0,039], thắng/hòa/thua 51/27/42. EX strict: McNemar p = 0,039, nghiêng về Ours.
- Ours với SDE-SQL: SQL Score chênh **+0,093**, CI95 [0,047; 0,139].

## Vì sao Ours điểm thấp: lỗi kỹ thuật, không phải do năng lực model

| Nhóm câu Ours | Số câu | Ours | CoT | SDE |
|---|---|---|---|---|
| Không sinh ra SQL (decompose lỗi) | 15 | **0,000** | 0,331 | 0,180 |
| Có SQL nhưng không thực thi | 20 | 0,389 | 0,310 | 0,205 |
| Thực thi được | 84 | **0,390** | 0,360 | 0,270 |

1. **Decompose không fail-open (15 câu, 12,6%, chấm 0).**
   - Contract lỗi gồm: "Unknown plan table", "Plan dropped a question obligation", "Invalid relational operation", "Detached plan step".
   - Linker đã có `link_fallback`, nhưng decompose thì chưa, nên cả câu kết thúc với `error`.
   - Giả định phản thực tế: nếu 15 câu này đạt điểm ngang CoT, Ours lên **0,382**, cao hơn CoT 0,348.
2. **Validator tĩnh bắt nhầm (20 câu không lên được BigQuery).**
   - `qualify(expand_stars=False)` không lần ra cột đi qua `alias.*` trong CTE, nên báo "Column X could not be resolved" (129 lượt). Replay với `expand_stars=True` gỡ chặn được 6/20 câu.
   - `_missing_join_key` báo "Missing composite icd_version JOIN" (114 lượt) dù SQL **đã join cả `icd_version`**. Lỗi xảy ra khi CTE mã dùng `UNION`, hoặc khi lọc bằng `EXISTS` hay `IN (SELECT …)`. Đã tái hiện bằng ví dụ tối thiểu.
   - Vòng repair (tối đa 2 lần) không thể sửa một lỗi không có thật, nên tiêu tốn LLM call vô ích.
3. **Selector vi phạm contract (18 câu `selection_fallback`, điểm TB 0,282).** Lỗi gồm "Verifier omitted obligations" và "Invalid verification status".
4. **Linker vẫn phải thử lại.** Lỗi gồm "Uncovered question literal" (cận tuổi) và "Requirements missing/too many". Linker chiếm khoảng 33% thời gian LLM của Ours.
5. **Câu easy.** Ours khớp số cột với gold tốt hơn CoT (31/36 so với 12/38), nhưng điểm rubric thấp hơn. Ours mất điểm ở logic lâm sàng (định nghĩa mã chẩn đoán, gender) và ở các câu không ra SQL.

## Đề xuất cải tiến (theo mức ưu tiên)

| # | Thay đổi | Loại | Ảnh hưởng dự kiến |
|---|---|---|---|
| 1 | Decompose fail-open: khi lỗi thì bỏ nhánh c2, vẫn chạy c1 và c3, ghi cờ `decompose_fallback` | Kỹ thuật (cùng nguyên tắc với link_fallback) | 15 câu có SQL; SQL Score ≈ +0,04 |
| 2 | Validator: `expand_stars=True`; luật composite nhận `UNION`, `EXISTS`, `IN (SELECT)` | Sửa bug | Tối đa 20 câu được thực thi; thêm cơ hội EX; ít repair hơn |
| 3 | Selector: chuẩn hóa output có tính quyết định (điền obligation thiếu thành `unknown`) trước khi kiểm contract | Kỹ thuật | Giảm selection_fallback |
| 4 | Linker: `normalize_linking` bao luôn literal số của khoảng tuổi | Kỹ thuật | Bớt lượt link thứ 2 (~50–230 s/lượt) |
| 5 | Chỉ dẫn chung: ưu tiên danh sách mã kèm `icd_version`, giống cách gold SQL làm | Thay đổi phương pháp (cần ghi rõ trong khóa luận) | Leaf diagnosis_codes |

Kiểm chứng: replay offline các trace đã lưu qua validator mới và viết unit test, trước khi chạy live.
Lưu ý về tính hợp lệ: các sửa đổi dựa trên kết quả validation. Đó là đúng chức năng của tập validation (dev), nhưng phải báo cáo trung thực. Phần internal_check và test vẫn được giữ làm số liệu cuối.
