# Kế hoạch thực nghiệm CLINSQL trên BigQuery — 13/11/2026

**Phạm vi chính từ 16/11/2026:** CLINSQL CoT + Self-Refinement, SDE-SQL và Ours. Giữ các bản ghi lịch sử MAC-SQL để tái lập các lượt cũ.

**Trạng thái 14/11/2026:** Phase C.1 CLINSQL CoT technical pilot
PASS 5/5 trên BigQuery thật theo approval riêng 16 GiB/SQL, 160 GiB tổng.
Chưa chấm official SQL/Execution Score. Phase C.1 không cấp quyền chạy 152/38
validation còn lại, 443 test, các phương pháp khác hoặc judge.
SDE-SQL và Ours vẫn cần fidelity/corpus/runner gates; các budget minh họa và
trạng thái cũ dưới đây không phải quyền thực thi hiện hành. Xem
`GPT5_MINI_LIVE_PILOT_RESULTS.md`.

**Cập nhật 14/11/2026:** Người dùng đã phê duyệt GPT-5-mini API cho chuỗi
thực nghiệm tháng 11 theo `UNLIMITED_RESEARCH_NOV_2026`, không có aggregate USD
hard cap nội bộ. Một nonclinical Responses access probe đã PASS, xem
`GPT5_MINI_ACCESS_CHECK.md`. Quyền này không tự phê duyệt patient-data BigQuery
SQL: hồ sơ Phase C.1 và tổng trần bytes BigQuery vẫn phải chốt riêng.
Pre-freeze master manifest đã khóa validation 152/38 và pilot 5; test chưa đọc.
Các đoạn mô tả dưới đây là kế hoạch gốc và có thể đã được cập nhật bởi status
hiện hành trong `IMPLEMENTATION_STATUS.md`.

**Trạng thái:** Phase A smoke đã PASS 4/4; chi tiết ở `PHASE_A_EXECUTION_RESULTS.md`. Phase B/C/D vẫn là kế hoạch và chưa được cấp quyền chạy pilot hay benchmark. Cả bốn phương pháp sẽ dùng cùng MIMIC-IV v3.1 trên project `kltn-text-to-sql`, hai datasets HOSP/ICU tại `US`, cùng manifest SHA-256 `46a816c289178f5b69470fef4cf335f1ff556ad1f4d40b83d600517d76a0ab5d` và SQL dialect BigQuery. Inference dùng câu hỏi tiếng Anh CLINSQL; không fine-tuning. Test gold/reference/rubric tách khỏi inference và retrieval.

## Phase A — bốn SQL smoke, chỉ sau phê duyệt riêng

`hosp_patients_count` cap 10 MiB; `icu_icustays_count` 10 MiB; `icu_hosp_join` 20 MiB; `clinsql_validation_043` 23 MiB; mỗi query timeout 30 giây, output một row. Dry run trước đó PASS 4/4, estimates tương ứng 0, 0, 5,123,888 và 20,032,585 bytes. Tổng *trần cấu hình* 63 MiB, tương đương khoảng **$0.000376** nếu tất cả bytes đều bị billed ở $6.25/TiB, trước free tier; đây không phải hóa đơn dự báo. Hai COUNT có thể được metadata tối ưu nên estimate 0. Không chạy lại nếu có marker `*.started` mà chưa kiểm tra job thủ công.

Nếu Phase A PASS, đối chiếu scalar result với metadata snapshot/reference validation nơi có sẵn, lưu job ID, actual bytes processed/billed, latency, SQL và status; result value nằm ở artifact ACL hạn chế. Không đưa result vào prompt hay OpenAI. Gold validation Easy/043 chỉ dùng trong phép smoke đã cho phép, không đưa vào inference. Hard/020 và `NTILE(5)` vẫn là rủi ro non-determinism cần ghi trong diagnostic, không sửa official scorer.

## Phase B — pipeline trên BigQuery bằng mock

- Dùng manifest thật làm Schema RAG authoritative; xây lại index khi metadata hash đổi. Kiểm tra 31 bảng, names/types, `datetimeevents`, JOIN keys và SQLGlot GoogleSQL.
- Nối **cùng** BigQuery adapter/gate/budget/logging vào CLINSQL CoT, SDE-SQL và Ours. Từng phương pháp giữ prompting, RAG, agent/candidate/probe/refinement riêng. Không đơn giản hóa thuật toán để đạt ngân sách; nếu quota chặn một phương pháp, dừng và báo thiếu fidelity.
- Chạy end-to-end bằng MockLLM và mock executor trước. Kiểm tra SQLGuard, dry run, timeout, bytes cap, permission errors, marker/resume, artifact ACL và không có gold/reference/rubric trong inference. Chưa kết nối thật khi data policy chưa chốt.
- Hoàn thiện durable budget ledger/checkpoint cho batch, token/API budget và judge budget độc lập; hiện chỉ có SQL budget trong một process và marker cho từng smoke.
- Xác minh round-trip artifact của các kiểu BigQuery có thể gặp trong CLINSQL (DATE/TIMESTAMP/NUMERIC/ARRAY/STRUCT và NULL) trước khi re-score hàng loạt; Phase A mới kiểm tra scalar aggregates.

**Trạng thái lịch sử ở Phase B:** CLINSQL CoT có prompt/SQL cleaner từ source gốc và hai refinement opportunities nhưng còn khác native ở dry run/error filtering; chưa xác nhận score parity. MAC-SQL có Selector → Decomposer → Refiner mock nhưng thiếu pruning threshold, column-value sampling, FK formatting và điều phối native đầy đủ. SDE-SQL có hai tầng probes, chín candidates và một số refinement paths mock; còn thiếu subquery/probe refinement đầy đủ, consistency tie-break và judge ba phiếu. Ours có Schema/ICD/Few-shot RAG, generation/validation/self-correction mock; corpus ICD/few-shot và schema index thật chưa khóa. Không phương pháp nào đủ điều kiện báo benchmark score chính thức. Xem `BASELINE_ADAPTATION.md` và `PAPER_ALGORITHM_AUDIT.md`.

## Phase C — pilot validation, cần ngân sách và data policy riêng

Sau Phase B và quyết định về input LLM, probe evidence, storage/retention, chạy CLINSQL CoT trên 5–10 validation cases với GPT-5-mini; SDE-SQL và Ours chỉ pilot khi fidelity đủ. Ghi model snapshot/config, prompt/index hash, calls, tokens, latency, BigQuery jobs/bytes và chi phí inference riêng với judge. Chấm lại predictions đã lưu, không gọi lại generation. Không dùng test để chỉnh prompt hoặc retrieval. Nếu probe evidence phải bị giới hạn bởi policy, công bố `adapted/restricted` và không gọi là reproduction nguyên bản.

Ngân sách mẫu để thảo luận: 10 câu × tối đa 3 SQL attempts × 64 MiB/query = **1,920 MiB** hoặc khoảng **$0.0114** BigQuery on-demand ở $6.25/TiB trước free tier. Đây chỉ là **kịch bản giả định**, chưa phải cap được duyệt; SQL thực tế có thể đòi cap khác theo dry run. Ngân sách GPT-5-mini/judge cần chốt giá API, token ceilings và ước tính từ pilot; hiện chưa có dữ liệu usage thật nên không ghi một USD giả định. Giữ ngân sách judge tách khỏi inference.

## Phase D — 190 validation, rồi 443 test sau khi khóa

Tổng 633 câu hỏi qua ba hệ thống chính. Validation dùng development và internal-check theo split đã chốt; test chỉ chạy khi model, prompt, code, schema index, config, retrieval và evaluator đã khóa. Mỗi batch cần dry-run dự toán, per-SQL cap, bytes/calls/probes/question, aggregate BigQuery cap, token/API cap, judge cap, checkpoint và stop-on-budget-exceeded. Không tự tăng cap. Mỗi case có run ID bất biến và kết quả đã hoàn thành được resume từ artifact/log, không tự gọi lại API hoặc SQL. Phải kiểm tra các trường hợp gần trùng để tránh few-shot leakage.

Kịch bản trần **minh họa, không phải dự toán được duyệt**: 633 × 3 × 30 SQL calls × 64 MiB = 3,646,080 MiB (khoảng 3.48 TiB), khoảng **$21.73** trước free tier ở $6.25/TiB. Số calls của SDE-SQL phụ thuộc algorithm fidelity và probes, nên không lấy 30 làm giới hạn thực thi trước khi kiểm chứng source và policy. Phải dùng dry run từng candidate/batch để lập ngân sách thực tế. Giá on-demand, 1 TiB free tier theo billing account/tháng và mức tối thiểu billed do Google công bố; free tier còn lại, cache, storage và phí LLM/judge chưa biết. [Nguồn giá BigQuery](https://cloud.google.com/bigquery/pricing).

## Điều kiện không được bỏ qua

- IAM vẫn `READ_ONLY_LIKELY`; cần verified ancestor IAM hoặc risk acceptance có thẩm quyền, trong phạm vi và thời hạn rõ. Phase A approval không tự mở Phase C/D. Không dùng Owner credentials và không tạo service account key.
- Chưa có quyết định được phép gửi schema, SQL errors, clinical values, probe outputs hay result rows đến LLM; mặc định không gửi raw patient data. Result artifacts cần ACL và retention được phê duyệt.
- Official CLINSQL SQL Score và Execution Score không bị thay; comparison policy FLOAT/NULL/duplicates/unordered chỉ cho diagnostic. Evaluator/judge configuration phải khóa; không dùng test rubric để inference.
- SDE-SQL fidelity gaps và shared real runner là blockers trước full benchmark. Nếu không tái hiện trung thực do data/API/cost, báo rõ adaptation thay vì đưa điểm như paper reproduction.
- Hệ thống tiếng Việt hoãn riêng; source gốc ba paper, gold SQL và reference results không sửa.
