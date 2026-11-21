# Thí nghiệm phụ trên BIRD (gpt-4o-mini)

Các script phân tích và ablation dùng cho khóa luận. Mọi quyết định thiết kế chỉ dựa trên tập tuning 300 câu (`results/omnisql/ours/splits.json`); gold SQL chỉ dùng để chấm, không bao giờ vào prompt. Chạy bằng `.venv_bird/Scripts/python.exe` từ thư mục gốc repo.

| Script | Việc | API | Output |
|---|---|---|---|
| `oracle_v8.py` | Tỷ lệ câu có ít nhất 1 candidate v8 đúng (oracle) | không | `v8/oracle_candidates.json` |
| `baseline_sample_analysis.py` | Thực thi greedy + 8 mẫu baseline, phân loại lỗi | không | `gpt-4o-mini-2024-07-18/baseline_sample_analysis.json` |
| `v9_candidate_executions.py` | Thực thi mọi candidate v9 (phân tích cùng ngân sách 8 mẫu) | không | `v9/candidate_executions.json` |
| `column_counts.py` | Số cột output gold vs candidate | không | `v9_lab/ncols.json` |
| `descriptions_exp.py` (+ `descriptions_eval.py`) | Thêm mô tả cột/giá trị BIRD vào DDL, 8 mẫu | ~$0,4 | `v9_lab/desc_samples_n8.jsonl` |
| `repair_colrule_exp.py gen\|repair\|eval` | Hướng 1: sửa mọi mẫu lỗi/rỗng trước vote (cả baseline, đối chứng đối xứng); hướng 2: quy tắc căn cột | ~$0,83 | `v9_lab/fix_exp/` |

Kết quả tuning (vote đúng /300, 8 mẫu): Ours A 194, Ours B 190, baseline 196; +repair: 194 / 192 / 196; quy tắc cột 194 (+repair 194). Không hướng nào thay đổi vote có ý nghĩa (mọi p ≥ 0,5) nên không chạy full.

## Thêm (2026-11-21)

| Script | Việc | API | Output |
|---|---|---|---|
| `draws_and_budget.py score\|report` | Lần lấy mẫu 2, baseline 16/17 mẫu, mẫu baseline bỏ phiếu theo quy tắc Ours; McNemar. **Cần `PYTHONUTF8=1`** (bộ chấm tác giả mở `dev.json` không chỉ định encoding). Chạy từng cấu hình một: chạy song song với job khác đã gây `MemoryError` | không | `draws_and_budget/` |
| `scaling_curve.py exec\|curve\|cost` | EX theo số mẫu k = 1…64 (bootstrap khi k > 16), oracle, chi phí theo token thực | không | `scaling/` |
| `v10_value_filter_offline.py [held_out]` | Sàng lọc miễn phí tầng lọc literal của v10 trên ứng viên v9 đã lưu | không | `v9/v10_value_filter_*.json` |

Ours v10 (`src/ehrqa/bird/ours_v10.py`, biến thể `v10*` trong `run_ours_bird.py`) đã viết và có test offline, **chưa chạy**.
| `update_baseline_ladder.py` | Bảng nâng cấp baseline từng bước ub0 → ub7 (mỗi bậc một thay đổi, McNemar với bậc trước và với ub0). Đọc file per-question do `draws_and_budget.py score ... ub3_repair ub4_plan` tạo | không | `draws_and_budget/update_baseline_ladder.json` |

`update_baseline` (`src/ehrqa/bird/update_baseline.py`, biến thể `ub0_baseline` … `ub7_pairwise` trong `run_ours_bird.py`): baseline OmniSQL được nâng cấp lần lượt từng thay đổi; ub5 = Ours v9, ub7 = Ours v10. Bậc 0–5 đo được từ dữ liệu đã lưu, không cần API.
