# Protocol nghiên cứu Text-to-SQL trên CLINSQL 2026

**Phạm vi chính từ 16/11/2026:** CLINSQL CoT + Self-Refinement, SDE-SQL và Ours. Manifest v2 khóa đúng ba hệ thống trên các câu đã chọn. MAC-SQL chỉ được lưu trong hồ sơ lịch sử.

**Cập nhật Phase C.2 14/11/2026:** CLINSQL CoT technical pilot đã có 5/5
predictions thực thi BigQuery và artifacts được audit; diagnostic strict
result shape/name match 0/5 nhưng không phải điểm CLINSQL. Người phụ trách
chưa phê duyệt truyền result rows tới Azure GPT-5-Chat, do đó official
SQL Score/Execution Score tạm `OFFICIAL_SCORE_NOT_AVAILABLE`. Các công việc
fidelity/retrieval/checkpoint offline tiếp tục; phase full validation/test
và official judge vẫn phải qua gate riêng. Xem
`PILOT_5_ACCURACY_EVALUATION.md` và `results/phase_c2_status.json`.

**Trạng thái 13/11/2026:** source chính thức của CLINSQL, MAC-SQL, SDE-SQL đã tải và khóa; 190 validation và 443 test đã kiểm kê. Metadata BigQuery 31/31 bảng PASS; bốn SQL Phase A đã thực thi tuần tự bằng reader Service Account với scoped risk acceptance và **4/4 PASS**. Đây là SQL smoke, chưa phải inference/evaluation benchmark. Bốn workflow vẫn ở mức mock; MAC-SQL/SDE-SQL chưa đủ fidelity để báo điểm. Chưa gọi model hoặc scorer chính thức. Xem `PHASE_A_EXECUTION_RESULTS.md`, `RESEARCH_VALIDITY_REGRESSION_REPORT.md` và `FULL_BENCHMARK_EXECUTION_PLAN.md`.

| Nội dung | Giá trị |
| --- | --- |
| Primary benchmark | CLINSQL 2026, snapshot nguồn chính thức phải khóa hash |
| Primary task | English Text-to-SQL, câu hỏi gốc không dịch |
| Database | MIMIC-IV v3.1 / BigQuery; project/billing `kltn-text-to-sql`, HOSP `mimiciv_3_1_hosp`, ICU `mimiciv_3_1_icu`, location `US`; 31-table manifest authoritative đã xác minh |
| LLM | GPT-5-mini, khóa model ID/version nếu API hỗ trợ |
| Fine-tuning | Không |
| Primary metrics | CLINSQL SQL Score và Execution Score theo evaluator chính thức |
| Efficiency metrics | Inference cost/query, calls/query, input/output tokens, latency/query; evaluation cost riêng |
| Baselines | CLINSQL CoT + Self-Refinement; SDE-SQL zero-shot SQL probes |
| Test policy | Chỉ chạy sau khi khóa cấu hình; không dùng test gold/rubric để sinh hoặc chỉnh hệ thống |
| Data policy | Không truyền dữ liệu MIMIC hạn chế truy cập lên API khi chưa được phép |

## Nguồn và quyền truy cập

- Nguồn benchmark: https://github.com/Barryshen1/ClinSQL và https://huggingface.co/datasets/yifeis02/ClinSQL. Ghi commit, hash từng file và split trước lượt chạy.
- Nguồn database: đúng MIMIC-IV v3.1 trong BigQuery. Dùng manifest cột/type dựng từ dataset `INFORMATION_SCHEMA`, có version/hash và khóa trước pilot. PostgreSQL/MIMIC Mini đã tắt ở CLI; schema Mini không còn là nguồn dữ liệu của CLINSQL.
- Cả bốn hệ thống nhận cùng câu hỏi tiếng Anh, cùng schema metadata/mô tả/JOIN hợp lệ và cùng chính sách truy cập. Không đưa gold SQL, gold results hoặc test rubric vào context inference.
- Probe chỉ read-only SELECT/CTE, dry run, bytes billed cap, timeout và result limit. Trước khi xác minh quyền truyền dữ liệu, runner không gửi raw rows, clinical values hoặc thống kê MIMIC lên OpenAI. Nếu giới hạn này làm SDE-SQL khác thuật toán gốc, gắn nhãn **adapted/restricted**, không gọi là reproduction trung thực.

## Splits, retrieval và khóa test

Validation được chia cố định thành development và internal-check bằng ID + seed, lưu manifest/hash. Mọi thay đổi prompt, retrieval, tham số và code chỉ dựa trên validation. Few-shot index loại câu đích, câu trùng chuẩn hóa, và mọi ví dụ có gold/result thuộc internal-check hoặc test. Index phải khóa hash trước test. Test chỉ chạy sau khi model, prompt, source, dependencies, schema, index, evaluator và judge config đã khóa; không chọn hệ thống bằng kết quả test.

## Các hệ thống cần chạy

1. **CLINSQL CoT + Self-Refinement:** giữ prompt generation/refinement và tối đa hai refinement theo paper/code chính thức. Chỉ cung cấp lỗi đã redacted; nếu protocol gốc yêu cầu phản hồi chứa dữ liệu không được phép, ghi adaptation.
2. **SDE-SQL:** giữ schema/value linking, SQL probes trước generation và probes khi refinement, zero-shot generation, không SFT. Không bỏ probes hay self-consistency để giảm chi phí. Nếu chính sách dữ liệu chặn probe evidence cần thiết, dừng và báo blocker.
3. **Hệ thống đề xuất:** giữ pipeline full agentic hiện tại, thêm adapter BigQuery/English riêng; tắt translation và SQL-result-to-Vietnamese-text trong benchmark runner, giữ code ứng dụng.

## Interface chung và logging

Mỗi phương pháp dùng cùng `DatabaseInterface` (schema, `dry_run`, `probe`, `execute`) và cùng `EvaluationInterface`. Chỉ evaluator chính thức của CLINSQL tính hai metric chính; kiểm tra SQL cú pháp hoặc kết quả query cục bộ chỉ là diagnostic. Ghi riêng status lỗi DB, lỗi API, SQL rỗng hợp lệ và abstention.

Mỗi record phải có query ID, split, method, source/config hashes, prediction SQL, trạng thái, trace công đoạn, số API calls, model ID thực trả về, input/output tokens, độ trễ, số lần execution/dry-run/probe, estimated bytes billed, inference cost, evaluation cost. Persist prediction trước khi chấm; resume chỉ dùng record cùng protocol hash, không gọi lại API cho record hoàn tất.

## Trình tự và điều kiện mở khóa

1. Audit dependency cũ; không còn runtime EHRSQL.
2. Dựng CLINSQL adapter offline và kiểm tra split/leakage.
3. Dựng DB/evaluation interface; kết nối BigQuery sau khi người dùng cung cấp thông tin và quyền.
4. Tái hiện CLINSQL CoT trước, xác minh prompt và refinement bằng test không chứa dữ liệu MIMIC.
5. Chuyển hệ thống đề xuất sang BigQuery/English, xác minh chức năng.
6. Source SDE-SQL gốc đã tải và khóa ngay để nghiên cứu; port sang CLINSQL/BigQuery/GPT-5-mini chỉ sau khi kiểm chứng pipeline, chính sách probe và chi phí. Không sửa source gốc để giảm thuật toán.
7. Pilot nhỏ trên validation; phân tích lỗi và ngân sách. Khóa cấu hình trước test chính thức.

## Báo cáo

Báo cáo SQL Score và Execution Score theo cùng evaluator/judge, paired difference theo cùng query ID, phân tầng difficulty/domain, và chi phí/độ trễ. Tách số liệu validation, internal-check và test. Không so trực tiếp điểm BIRD/Spider lịch sử với CLINSQL. Không khẳng định cải thiện trước khi có lượt chạy đầy đủ, protocol cố định và kiểm tra leakage.

**Ghi nhận khi kết thúc Phase A:** Phase A SQL smoke đã PASS nhưng IAM vẫn `READ_ONLY_LIKELY` vì không xem được Organization/Folder inheritance; project-level risk acceptance chỉ bao phủ đúng bốn smoke SQL. Chính sách truyền probe evidence/clinical values lên LLM, benchmark-scoped approval, durable batch budget/resume, scorer thật và model/judge budget vẫn chưa chốt. Ở thời điểm đó chưa có điểm rubric. Xem [kết quả Phase A](PHASE_A_EXECUTION_RESULTS.md).
