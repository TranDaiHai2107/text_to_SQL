# Protocol nghiên cứu Text-to-SQL trên CLINSQL 2026

**Trạng thái:** đã tải snapshot repo chính thức CLINSQL tại commit `1d819960eb3ce3ac0e9beb4e801810a05735fd58` vào `external/clinsql_official/` (Git ignore). Đã kiểm kê 190 câu validation và 443 câu test. Chưa nối BigQuery, scorer hoặc chạy inference. Không được báo cáo điểm test từ trạng thái này.

| Nội dung | Giá trị |
| --- | --- |
| Primary benchmark | CLINSQL 2026, snapshot nguồn chính thức phải khóa hash |
| Primary task | English Text-to-SQL, câu hỏi gốc không dịch |
| Database | MIMIC-IV v3.1 / BigQuery cho hệ thống đích và benchmark; project/dataset/location chờ xác minh |
| LLM | GPT-5-mini, khóa model ID/version nếu API hỗ trợ |
| Fine-tuning | Không |
| Primary metrics | CLINSQL SQL Score và Execution Score theo evaluator chính thức |
| Efficiency metrics | Inference cost/query, calls/query, input/output tokens, latency/query; evaluation cost riêng |
| Baselines | CLINSQL CoT + Self-Refinement; MAC-SQL Selector + Decomposer + Refiner; SDE-SQL zero-shot SQL probes |
| Test policy | Chỉ chạy sau khi khóa cấu hình; không dùng test gold/rubric để sinh hoặc chỉnh hệ thống |
| Data policy | Không truyền dữ liệu MIMIC hạn chế truy cập lên API khi chưa được phép |

## Nguồn và quyền truy cập

- Nguồn benchmark: https://github.com/Barryshen1/ClinSQL và https://huggingface.co/datasets/yifeis02/ClinSQL. Ghi commit, hash từng file và split trước lượt chạy.
- Nguồn database: đúng MIMIC-IV v3.1 trong BigQuery. Ghi project, dataset, region, schema snapshot, quyền và phiên bản dữ liệu; PostgreSQL/MIMIC Mini là triển khai cũ, không còn là database mục tiêu và không dùng để báo điểm CLINSQL.
- Cả bốn hệ thống nhận cùng câu hỏi tiếng Anh, cùng schema metadata/mô tả/JOIN hợp lệ và cùng chính sách truy cập. Không đưa gold SQL, gold results hoặc test rubric vào context inference.
- Probe chỉ read-only SELECT/CTE, dry run, bytes billed cap, timeout và result limit. Trước khi xác minh quyền truyền dữ liệu, runner không gửi raw rows, clinical values hoặc thống kê MIMIC lên OpenAI. Nếu giới hạn này làm SDE-SQL khác thuật toán gốc, gắn nhãn **adapted/restricted**, không gọi là reproduction trung thực.

## Splits, retrieval và khóa test

Validation được chia cố định thành development và internal-check bằng ID + seed, lưu manifest/hash. Mọi thay đổi prompt, retrieval, tham số và code chỉ dựa trên validation. Few-shot index loại câu đích, câu trùng chuẩn hóa, và mọi ví dụ có gold/result thuộc internal-check hoặc test. Index phải khóa hash trước test. Test chỉ chạy sau khi model, prompt, source, dependencies, schema, index, evaluator và judge config đã khóa; không chọn hệ thống bằng kết quả test.

## Các hệ thống cần chạy

1. **CLINSQL CoT + Self-Refinement:** giữ prompt generation/refinement và tối đa hai refinement theo paper/code chính thức. Chỉ cung cấp lỗi đã redacted; nếu protocol gốc yêu cầu phản hồi chứa dữ liệu không được phép, ghi adaptation.
2. **MAC-SQL:** giữ Selector, Decomposer, Refiner; không dùng SQL-Llama fine-tuned. Port sang BigQuery/GPT-5-mini, ghi từng khác biệt trong `BASELINE_ADAPTATION.md`.
3. **SDE-SQL:** giữ schema/value linking, SQL probes trước generation và probes khi refinement, zero-shot generation, không SFT. Không bỏ probes hay self-consistency để giảm chi phí. Nếu chính sách dữ liệu chặn probe evidence cần thiết, dừng và báo blocker.
4. **Hệ thống đề xuất:** giữ pipeline full agentic hiện tại, thêm adapter BigQuery/English riêng; tắt translation và SQL-result-to-Vietnamese-text trong benchmark runner, giữ code ứng dụng.

## Interface chung và logging

Mỗi phương pháp dùng cùng `DatabaseInterface` (schema, `dry_run`, `probe`, `execute`) và cùng `EvaluationInterface`. Chỉ evaluator chính thức của CLINSQL tính hai metric chính; kiểm tra SQL cú pháp hoặc kết quả query cục bộ chỉ là diagnostic. Ghi riêng status lỗi DB, lỗi API, SQL rỗng hợp lệ và abstention.

Mỗi record phải có query ID, split, method, source/config hashes, prediction SQL, trạng thái, trace công đoạn, số API calls, model ID thực trả về, input/output tokens, độ trễ, số lần execution/dry-run/probe, estimated bytes billed, inference cost, evaluation cost. Persist prediction trước khi chấm; resume chỉ dùng record cùng protocol hash, không gọi lại API cho record hoàn tất.

## Trình tự và điều kiện mở khóa

1. Audit dependency cũ; không còn runtime EHRSQL.
2. Dựng CLINSQL adapter offline và kiểm tra split/leakage.
3. Dựng DB/evaluation interface; kết nối BigQuery sau khi người dùng cung cấp thông tin và quyền.
4. Tái hiện CLINSQL CoT trước, xác minh prompt và refinement bằng test không chứa dữ liệu MIMIC.
5. Chuyển hệ thống đề xuất sang BigQuery/English, xác minh chức năng.
6. Sau kiểm chứng pipeline và chi phí, tích hợp MAC-SQL/SDE-SQL đúng thuật toán.
7. Pilot nhỏ trên validation; phân tích lỗi và ngân sách. Khóa cấu hình trước test chính thức.

## Báo cáo

Báo cáo SQL Score và Execution Score theo cùng evaluator/judge, paired difference theo cùng query ID, phân tầng difficulty/domain, và chi phí/độ trễ. Tách số liệu validation, internal-check và test. Không so trực tiếp điểm BIRD/Spider lịch sử với CLINSQL. Không khẳng định cải thiện trước khi có lượt chạy đầy đủ, protocol cố định và kiểm tra leakage.

**Blocker hiện tại:** dataset/scorer nguồn đã có nhưng adapter chưa đọc layout gốc và evaluator chưa nối code chính thức; chưa có BigQuery project/dataset/region, quyền MIMIC và chính sách truyền probe evidence; chưa khóa judge và model availability/cost. Không chạy inference, probes thật hay evaluator trả phí trước khi các mục này được xác minh.
