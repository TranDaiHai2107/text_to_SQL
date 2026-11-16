# Đối chiếu code gốc của ba baseline

Kiểm tra ngày 12/11/2026. Commit và hash của ba checkout nằm trong [`PAPER_SOURCE_LOCK.json`](../PAPER_SOURCE_LOCK.json); chạy `python paper_sources.py` để xác minh trước khi chạy inference. Đây là audit đường thực thi, không phải xác nhận kết quả paper đã được tái hiện trên CLINSQL.

## CLINSQL 2026: CoT + Self-Refinement

Nguồn thực thi: `external/clinsql_official/model_inference/clinical_sql_benchmark_evaluator_CoT.py`, `utils/prompt_utils.py`, `utils/sql_utils.py`, `evaluation/clinical_rubric_scorer.py`.

1. Đọc `query_*.txt`; không cần SQL/rubric để sinh SQL (`process_single_query`, dòng 422–429).
2. `SQLGenerator.generate_sql` dùng `build_generation_prompt` và schema MIMIC; `clean_sql_response` xử lý output.
3. Thực thi BigQuery một lần. Chỉ khi thực thi thất bại mới gọi `build_refinement_prompt` và thử lại, mặc định tối đa hai lượt sửa (dòng 458–480).
4. Ghi SQL, kết quả và từng attempt. Rubric scorer là bước đánh giá riêng, có judge API riêng; chưa được nối vào runner chung.

Adapter mới `src/ehrqa/clinsql/dataset.py::load_official_questions` chỉ đọc câu hỏi từ cây thư mục gốc. `cot.py` gọi trực tiếp hai hàm prompt và SQL cleaner từ checkout gốc. `cot_runner.py` giữ ba lần thử và điều kiện sửa khi lỗi SQL. Nó còn khác source gốc ở dry run, giới hạn quyền truy cập, lọc thông báo lỗi trước khi gửi LLM, cách ghi usage, và chưa nối Azure/OpenAI transport/scorer. Vì vậy **chưa thể gọi runner chung là reproduction đầy đủ**.

## MAC-SQL 2025: Selector → Decomposer → Refiner

Nguồn thực thi: `external/mac_sql_official/core/chat_manager.py`, `core/agents.py`, `core/const.py`, `run.py`.

1. `ChatManager.start` chuyển message qua Selector, Decomposer, Refiner cho tới khi trả về System (`chat_manager.py`, dòng 22–58).
2. Selector đọc schema/foreign keys và có thể prune; đường mặc định lấy các giá trị cột từ SQLite để chọn schema (`agents.py`, dòng 42–597). `--without_selector` và `--use_gold_schema` là ablation/oracle, không dùng trong so sánh chính.
3. Decomposer sinh SQL từ template BIRD/Spider và câu hỏi (`agents.py`, dòng 598–660).
4. Refiner chạy SQL, sửa lỗi thực thi, và với đường BIRD còn sửa trường hợp rỗng/NULL (`agents.py`, dòng 661–786). Vòng agent có giới hạn `MAX_ROUND` trong `core/const.py`.

Native CLI chỉ nhận `bird`/`spider`; database và schema là SQLite; OpenAI SDK gốc pin `0.28.1` và Azure GPT-4. `run.py` có `--use_gold_schema` và truyền `ground_truth` trong message; port CLINSQL phải bảo đảm gold không vào prompt/LLM và không dùng oracle schema. Các truy vấn lấy giá trị cột của Selector cần chính sách probe chung; nếu không được phép trả clinical values cho LLM, **chưa thể tuyên bố port trung thực**. `clinsql/baselines/mac_sql.py` nay có đường mock qua ba agent, nhưng chưa đạt parity pruning/value sampling của source.

## SDE-SQL 2026: exploration → generation → refinement

Nguồn thực thi: `external/sde_sql_official/src/gpt_request.py`, `src/explore_new.py`, `src/refine_new.py`, `run/run_qwen_eval_template.sh`.

1. Script mẫu chọn `qwen-max`, `try_num=3`, bật probe, refine và self-consistency; không đồng nghĩa đã dùng GPT-5-mini.
2. Khi `use_probe` và có `knowledge_list`, `probe_before_generation` tạo SQL probes, chạy chúng, đưa evidence vào prompt (`gpt_request.py`, dòng 576–600; `explore_new.py`, dòng 450+). Probe trả nhãn NULL/Not NULL hoặc lỗi SQLite.
3. Khi self-consistency bật, generation yêu cầu 9 SQL candidates rồi chọn bằng execution consistency (`gpt_request.py`, dòng 611–618).
4. `refine_sql` trong `refine_new.py` tiếp tục dùng probes và judge; các lần thử ngoài do `try_num` điều khiển (`gpt_request.py`, dòng 560–690).

Các chỗ cần sửa rõ ràng trước port: entrypoint ép `args.use_selected_examples=True` và đọc `data/match_examples.json` (dòng 1017–1027), nhưng file không có trong checkout; hàm `collect_response_from_gpt` lại đặt `examples_list=None` (dòng 487). Đường native còn nhận `gt_list` và có nhánh `use_gt` (`gpt_request.py`, dòng 266–305), và gọi `execute_model(sql, gt_list[i], ...)` trong quá trình sinh để quyết định ghi log (dòng 639). Cần cắt mọi đường dùng gold ở inference CLINSQL, giữ riêng cho evaluation. `clinsql/baselines/sde_sql.py` nay kiểm thử hai probe stages, 9 candidates và hai nhánh refinement bằng mock; prompt gốc được tải tĩnh và thay phần SQLite dialect. Phân rã subquery, judge ba phiếu và chọn candidate chưa tương đương source. Probe BigQuery thật vẫn cần ngân sách và chính sách truyền dữ liệu. Nếu chỉ cho phép schema/lỗi đã lọc, phải ghi tên biến thể **adapted/restricted**.

## Cổng kiểm chứng trước pilot

- Chạy adapter với đúng 190 câu validation; test 443 câu vẫn khóa.
- Ghi manifest gồm source commit, hash câu hỏi, model snapshot/config, prompt hash, policy probe, schema snapshot, code commit và chi phí.
- Kiểm tra bằng mock cho số lần gọi, thứ tự agent/probe, SQL dialect và việc không đưa gold vào inference.
- Chỉ sau khi có BigQuery đúng MIMIC-IV v3.1, quyền truy cập và giới hạn chi phí mới pilot validation; không chạy native script mặc định trên test.
