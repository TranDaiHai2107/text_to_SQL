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
