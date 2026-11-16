# Source gốc của ba hệ thống paper

Ngày 12/11/2026. Source được clone nguyên bản vào `external/`, Git ignore và khóa trong [`PAPER_SOURCE_LOCK.json`](../PAPER_SOURCE_LOCK.json). `python paper_sources.py` xác minh commit/tree, tracked worktree, hash các entrypoint và số câu CLINSQL. Ba môi trường riêng đã cài và mở được native CLI `--help`; chưa gọi model, BigQuery hoặc scorer. Đây là **source chính thức nguyên bản**, chưa phải ba baseline đã chạy thành công trên CLINSQL/GPT-5-mini.

## 1. CLINSQL CoT + Self-Refinement

- Source: [`external/clinsql_official`](../external/clinsql_official), commit `1d819960eb3ce3ac0e9beb4e801810a05735fd58`.
- Benchmark: `data/splits/validation` 190 câu, `data/splits/test` 443 câu, mỗi câu có question/gold SQL/rubric/results. `outputs/` của tác giả là kết quả lịch sử; không đưa vào inference hoặc chấm lại prediction của mình.
- Generation/refinement gốc: `model_inference/clinical_sql_benchmark_evaluator_CoT.py`; prompt tại `utils/` và runner `model_inference_scripts/run_proprietary_models.sh`. Code hỗ trợ alias GPT-5-mini qua Azure OpenAI, BigQuery và tối đa hai refinement mặc định. Scorer: `evaluation/clinical_rubric_scorer.py`.
- Cách chạy gốc theo README: `bash model_inference_scripts/run_proprietary_models.sh GPT-5-mini`, rồi `python evaluation/clinical_rubric_scorer.py full <model_name>`. **Không chạy các lệnh này trước khi khóa quyền, chi phí, split và cấu hình; mặc định có thể duyệt nhiều câu.**
- Cần xác minh schema BigQuery, project/billing, credentials, model deployment, judge config và chính sách dữ liệu trước pilot validation.

## 2. MAC-SQL

- Source: [`external/mac_sql_official`](../external/mac_sql_official), commit `31a9df5e0d520be4769be57a4b9022e5e34a14f4`.
- Thuật toán: `core/agents.py` chứa Selector, Decomposer, Refiner; `core/chat_manager.py` điều phối; `core/const.py` prompt; `run.py` nhận `dataset_name` là `bird` hoặc `spider`.
- Runtime gốc dùng OpenAI SDK `0.28.1` và GPT-4/Azure config. Data BIRD/Spider SQLite tải riêng theo README; repo clone chưa chứa đủ database để chạy lại điểm paper. Phần SQL-Llama fine-tuned không dùng trong so sánh không fine-tune.
- Trạng thái: **đã khóa source, chưa tái hiện lượt inference gốc**. Chuyển sang GPT-5-mini/CLINSQL/BigQuery cần adaptation được ghi ở [`BASELINE_ADAPTATION.md`](BASELINE_ADAPTATION.md); không bỏ Selector, Decomposer hay Refiner.

## 3. SDE-SQL

- Source: [`external/sde_sql_official`](../external/sde_sql_official), commit `e425408fcb13d69b0bd15f917b819591805a8973`.
- Thuật toán: `src/gpt_request.py` điều phối, `src/explore_new.py` tạo và thực thi probes, `src/refine_new.py` sửa lỗi; prompt và config nằm trong `src/`. Script gốc `run/run_qwen_eval_template.sh` bật `use_probe=True`, `use_refine=True`, `use_selfconsistency=True`.
- Runtime gốc nhận BIRD/Spider SQLite và mặc định `qwen-max`; file data thật cần được cung cấp riêng. Chưa có GPT-5-mini/BigQuery trong đường chạy gốc.
- Trạng thái: **đã khóa source, chưa tái hiện lượt inference gốc**. Port cần giữ probes trước generation, probes khi refinement và self-consistency. Quy định không gửi clinical values/statistics từ MIMIC lên API có thể ngăn tái hiện trung thực; khi đó dừng hoặc gắn nhãn adapted/restricted, không báo như nguyên bản.

## Ranh giới so sánh

Ba source gốc đã có và biên dịch cú pháp các entrypoint chính thành công. Chưa có kết quả trên cùng CLINSQL/GPT-5-mini. Chạy nguyên code MAC-SQL/SDE-SQL trên BIRD/Spider là phép tái hiện paper gốc; chuyển sang CLINSQL/BigQuery là phép so sánh mới và cần adapter, policy và audit riêng. Không dùng output mẫu của tác giả, gold SQL hoặc rubric test làm đầu vào inference.

## Môi trường chạy nguyên bản

Mỗi repo dùng **virtual environment riêng** vì dependency khác nhau: CLINSQL yêu cầu BigQuery/OpenAI; MAC-SQL pin `openai==0.28.1` và README dùng Python 3.9; SDE-SQL pin `sqlglot==25.6.1`. Không trộn các `requirements.txt` vào môi trường dự án. Xem [hướng dẫn và lock](../../environment/README.md). CLINSQL cài subset cho proprietary CoT/scorer; nhánh vLLM/open-source chưa cài vì không nằm trong so sánh GPT-5-mini.

Smoke check: cả ba `pip check` đều sạch; native CoT/scorer, MAC-SQL và SDE-SQL đều mở được `--help` trong venv riêng. Đây là kiểm tra import/CLI, không phải bằng chứng thuật toán chạy end-to-end hoặc điểm paper. Adapter của dự án đọc 190 câu validation trực tiếp từ source gốc bằng `python run.py clinsql-inspect --official-root external/clinsql_official`; không mở gold/rubric.

Trước khi cài/chạy, xác minh lại `python paper_sources.py`. Lệnh native của MAC-SQL nằm trong `run.bat`/`run.sh` nhưng mặc định chạy bộ `foo` của tác giả; lệnh SDE-SQL trong `run/run_qwen_eval_template.sh` mặc định `qwen-max`, không phải GPT-5-mini. Không dùng chúng để tuyên bố đã so sánh công bằng trên CLINSQL. CLINSQL native runner có thể xử lý cả split nếu gọi không giới hạn; không chạy trực tiếp trên test trước khi khóa protocol.
