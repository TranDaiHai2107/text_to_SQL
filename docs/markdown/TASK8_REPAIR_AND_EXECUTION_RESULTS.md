# Task 8 — kết quả sửa source fidelity và pilot

## Database preprocessing và phân loại payload

- **MAC preprocessing hoàn tất 225/225 slots.** Phát lại và kiểm chứng 109 job có bằng chứng tương thích. Kiểm tra 116 slot STRING còn thiếu theo SQL SHA-256 và khôi phục đúng 116 slot đó bằng dữ liệu distinct chưa lọc. Dùng formatter từ source khóa. Xác minh 116 job mới có 116 hash riêng và không trùng các hash truy vấn MAC lịch sử. Giữ nguyên 262 job và 54.639.198.208 billed bytes lịch sử.
- **Hai phạm vi ngân sách.** `DATABASE_PREPROCESSING_BUDGET` ghi riêng truy vấn lấy mẫu cấp database trong cùng ledger. `CASE_EXECUTION_BUDGET` giữ quota per-case cho inference và SQL runtime. Scope mới dùng cùng method cap, tổng ceiling và reader authorization, giữ nguyên quota lịch sử Easy/058. Sample job đã đối soát được replay cùng hash. Runner tái sử dụng sample map của database qua cả năm case trong cùng lần chạy.
- **Chi phí.** Trước submission, dry run cho 116 truy vấn ước tính 24.105.713.664 billed bytes và trần động 27.773.632.512 bytes, tương đương tối đa khoảng 4.080,91 VND. Scope còn 2.199.023.255.552 bytes tại thời điểm kiểm tra và dùng chung trần nghiên cứu 6.962.660,25 VND. Sau chạy, 116 job đã đối soát, **24.105.713.664 billed bytes**, khoảng **3.541,96 VND** trước free tier và credit, 0 pending. Không cấp thêm credit.
- **Source parity.** Database description thực tế khớp renderer BIRD gốc trên cùng schema, metadata, thứ tự và 225 sample slots. SHA-256 `63967c027c468d2af1b41f7469cba9d535c86584da2d696937f475dcef28cd4c`. Đối chiếu riêng 56 quan hệ trong manifest cho cùng chuỗi FK với source trên cùng input. Bằng chứng này bao phủ formatter và renderer, còn qualifier GoogleSQL, BigQuery error feedback và model parameter adaptation vẫn thuộc cấu hình đã ghi.
- **Ours Easy/058.** Đối chiếu đủ 24 mục với catalog khóa. Có 12 mục `d_icd_diagnoses`, 12 mục `d_icd_procedures`, gồm 23 ICD-10 và một ICD-9. `table`, `column`, `code_column` là định danh schema. `code`, `label`, `icd_version` là mã và thuật ngữ tĩnh. `id`, `source`, `match`, `aliases`, `candidate_list_complete` là định danh dictionary, nguồn gốc và metadata retrieval. Cả 24 đều không chứa quan sát, mẫu giá trị hay định danh bệnh nhân. Classifier đã phân biệt dữ liệu này với patient observations. Phần dictionary tĩnh vẫn xuất phát từ bản phát hành MIMIC-IV hạn chế, nên giữ nguyên payload và điều kiện egress.
- **Kết quả live.** Scope BUDGET của MAC đã được giải quyết. MAC **0/5** và Ours **0/5** SQL cuối có kết quả hoàn chỉnh. **0 GPT-5-mini calls mới.** Selector của MAC còn cần xác minh quyền và data controls cho mẫu giá trị MIMIC-IV qua đúng OpenAI project/Chat Completions. Linker Ours cần xác minh điều kiện tương ứng cho dictionary tĩnh qua Responses API. Cả hai yêu cầu xác minh kiểm soát retention, huấn luyện và human review cho phạm vi dữ liệu thực gửi. Checkpoint trước đó được giữ nguyên. [PhysioNet](https://www.physionet.org/news/post/llm-responsible-use/)
- **120 tests PASS** cho phạm vi sửa lần này. CoT/SDE và scorer giữ nguyên.



## Lượt trước — model compatibility và controlled execution

- **MAC compatibility: YES.** OpenAI Chat Completions trả `SELECT 1` qua một request tổng hợp và xác nhận snapshot `gpt-5-mini-2025-08-07`. Receipt ghi một user message, `n=1`, `store=false`, timeout 180 giây ở SDK và endpoint `https://api.openai.com/v1/chat/completions`. Adapter dùng mặc định của model, bỏ `temperature` và `top_p`, không đặt reasoning effort hoặc trần đầu ra trong request. Nhãn `MODEL_PARAMETER_COMPATIBILITY_ADAPTATION` được lưu cùng cấu hình và checkpoint. Source dùng `temperature=0.1`. Parameter parity chưa đạt EXACT.
- **MAC Easy/058 — BUDGET.** Sau khi kiểm tra transport, runner vào bước chuẩn bị mẫu và ghi `RESOURCE_BUDGET_BLOCKED`. Trong 225 slots, 109 có job phù hợp để replay và 116 STRING slots cần raw evidence. Case đã dùng đủ 225 probe reservations, còn **0** slots. Runner dừng trước dry run, BigQuery job mới và Selector. Chưa tạo database description đầy đủ hoặc SQL cuối. Cache và job IDs giữ nguyên, không phân bổ khoản thiếu sang case khác. Cần scope ngân sách lấy mẫu có thể bao phủ đúng phần phục hồi thiếu trước khi chạy lại. Việc đưa mẫu MIMIC-IV lấy từ patient tables vào prompt còn cần xác minh quyền egress cho đúng OpenAI project và Chat Completions.
- **Ours Easy/058 — DATA_EGRESS.** Checkpoint đã xác minh cho thấy linker tạo payload với 24 mục từ dictionary MIMIC-IV. Đây là dữ liệu dictionary lấy từ catalog hạn chế, khác với DDL và metadata tên bảng/cột. Thiếu xác minh quyền truyền và data-handling controls cho đúng OpenAI project trên Responses API, nên chưa gọi SDK. Structured Outputs đã qua kiểm tra tổng hợp ở lượt trước. Kiến trúc và catalog đóng băng giữ nguyên. Checkpoint lỗi đã biết được giữ lại và case không bị chạy lặp.
- **Kết quả và usage của lượt này:** MAC 0/5, Ours 0/5 final SQL/complete result artifacts. Có **1 GPT-5-mini request tổng hợp**, 12 input / 76 output tokens, trong đó 64 reasoning, ước tính 0,000155 USD theo rate đã khóa. Có 0 clinical API requests, 0 BigQuery jobs mới, 0 billed bytes mới, 0 SQL reservations pending. Ledger giữ 262 job MAC đã đối soát và 54.639.198.208 billed bytes lịch sử. CoT và SDE giữ artifacts cũ. Điều kiện mở bốn case còn lại chưa đạt.
- **Kiểm thử:** 126 tests PASS. Đã xác minh SHA-256 checkpoint MAC mới và Ours hiện có. Schema, model, hai ngân sách và user attestation trong MAC approval giữ nguyên scope. Cấu hình mới được ghim theo hash mới.


## Lượt sửa trước ngày 15/11/2026

- **MAC-SQL Easy/058:** preflight trả `PROVIDER_MODEL_INCOMPATIBLE` trước bước lấy mẫu mới và trước OpenAI SDK. Source MAC-SQL dùng Chat Completions, một user message và `temperature=0.1`. OpenAI ghi rõ GPT-5-mini không hỗ trợ tham số này. Adapter giữ yêu cầu nguồn và không tự đổi tham số hay model. **0/5** SQL cuối và **0/5** result artifacts. [Tài liệu tương thích của OpenAI](https://developers.openai.com/api/docs/guides/latest-model?model=gpt-5.4)
- **Ours Easy/058:** chạy tới linker với schema manifest 31 bảng, frozen few-shot và catalog thật đã kiểm SHA-256 `3fabb16dfc04a09e58fbbb752eaa17e5d1c8a4b8eff96cda98f6a6ac7016b5fc` trên **204.275** bản ghi. Payload linker có **24 mục từ điển MIMIC-IV**. SDK chưa nhận request vì `RESTRICTED_EVIDENCE_EGRESS`. Đã xác minh SHA-256 checkpoint của lượt này. **0/5** SQL cuối và **0/5** result artifacts. Structured Outputs, required fields, arrays, scalar IDs và kiểm tra yêu cầu lâm sàng giữ nguyên. Parity tests chạy offline. Request tổng hợp hợp lệ là bằng chứng từ lượt trước.
- **Chi phí tăng thêm:** 0 GPT-5-mini requests, 0 input/output tokens, 0 BigQuery query jobs, 0 billed bytes. Ledger Task 8 và Phase C.1 có 0 reservation pending hoặc unknown billing. Task 8 vẫn có 262 jobs MAC-SQL và 54.639.198.208 billed bytes từ các lượt cũ. Ledger Ours giữ một request tổng hợp cũ với 240 input và 497 output tokens. Hai case đầu chưa đạt điều kiện chạy tiếp.

## Lỗi đã sửa

- MAC-SQL gọi trực tiếp formatter `Selector._get_value_examples_str` và các helper ngày/email từ checkout đã khóa. Điều kiện email kiểu source, ngày giờ dạng chuỗi, thứ tự sample, NULL, blank, URL, độ dài và giới hạn giá trị số được kiểm bằng fixture chung. BigQuery kiểu date/time được biểu diễn bằng chuỗi giữ ngày, giờ và offset nếu có. STRING đi qua danh sách distinct chưa lọc ở SQL để formatter gốc nhìn thấy các giá trị phía sau sáu mẫu đầu. Column SQL hash cũ vẫn đối chiếu được.
- Renderer BIRD giữ nhãn nguồn nếu metadata cung cấp, dùng tên cột thật nếu thiếu nhãn và giữ thứ tự manifest. Refiner đổi từ SQLite sang BigQuery chỉ trong template trước khi điền câu hỏi, mẫu và lỗi. Điều này giữ nguyên chữ SQLite nếu nó xuất hiện trong evidence. Selector, Decomposer, parser và Refiner đối chiếu trực tiếp với source trên fixtures. Các quan hệ JOIN và tên đầy đủ BigQuery vẫn là phần chuyển dialect.
- Cache lookup ưu tiên query đúng semantics. Một job đã đối soát mà không đọc đủ sẽ báo lỗi thay vì gửi lại cùng SQL. Giữ nguyên SQL Guard, reader, dry run, bytes cap, kiểm đủ kết quả và reservation cũ.
- CoT có profile `SOURCE_ALIGNED_NEXT_RUN`, buộc 2.048 output tokens, bỏ override reasoning riêng để giữ wire setting của source, tách đường dẫn checkpoint, và dừng khi SQL Guard từ chối. Workflow vẫn tối đa hai lượt refinement cho lỗi SQL. Error feedback BigQuery vẫn lọc dữ liệu. Smoke ở trần 2.048 từng bị hết token với cấu hình reasoning medium của lượt cũ. Profile mới chưa chạy live.
- SDE-SQL giữ nguyên 5 artifacts và nhãn `SDE_GROUPED_3X3_REQUEST_ADAPTATION`. Bằng chứng đã lưu ghi Chat Completions từ chối một request `n=9` với giới hạn 8. Chín candidates trong ba request vẫn là cấu hình thích nghi. Workflow, probes, grading và selection SDE không đổi. [Bằng chứng giới hạn n](SDE_N9_ERROR_ROOT_CAUSE.md)

## Danh sách 116 cột STRING được khôi phục ở lượt preprocessing

Đối chiếu đúng 225 truy vấn theo manifest và SQL SHA-256 với các job đã đối soát trong scope pilot. **109** cột có job khớp truy vấn mới hoặc truy vấn distinct gốc đủ điều kiện đưa vào đường replay. Gồm 43 DATETIME, 3 DATE, 20 INT64, 27 FLOAT64 và 16 STRING. **116 cột STRING** chỉ có hash SQL bounded cũ với bộ lọc không tương đương. Chúng là tập ứng viên cần xác minh hoặc khôi phục, chưa có bằng chứng rằng cả 116 đều thực sự đổi ví dụ. Query mới cho các cột này cần dữ liệu distinct chưa lọc để áp đúng oracle. Lượt trước dừng ở inventory vì cấu hình inference nguồn bị provider chặn. Lượt model defaults xác minh thêm rằng Easy/058 đã hết quota probe. Cache cũ và mọi job ID vẫn nguyên vẹn.

Easy/058 đã dùng đủ 225 probe reservations trong lịch sử. Phần khôi phục đã được thực hiện bằng scope cấp database trong lượt cập nhật ở đầu báo cáo. Ràng buộc per-case vẫn áp dụng.

- `emar` (2) `medication`, `event_txt`
- `emar_detail` (29) `parent_field_ordinal`, `administration_type`, `barcode_type`, `reason_for_no_barcode`, `complete_dose_not_given`, `dose_due`, `dose_due_unit`, `dose_given`, `dose_given_unit`, `will_remainder_of_dose_be_given`, `product_amount_given`, `product_unit`, `product_code`, `product_description`, `product_description_other`, `prior_infusion_rate`, `infusion_rate`, `infusion_rate_adjustment`, `infusion_rate_adjustment_amount`, `infusion_rate_unit`, `route`, `infusion_complete`, `completion_interval`, `new_iv_bag_hung`, `continued_infusion_in_other_location`, `restart_interval`, `side`, `site`, `non_formulary_visual_verification`
- `hcpcsevents` (1) `short_description`
- `labevents` (5) `value`, `valueuom`, `flag`, `priority`, `comments`
- `microbiologyevents` (9) `spec_type_desc`, `test_name`, `org_name`, `quantity`, `ab_name`, `dilution_text`, `dilution_comparison`, `interpretation`, `comments`
- `omr` (2) `result_name`, `result_value`
- `patients` (3) `gender`, `anchor_year_group`, `dod`
- `pharmacy` (14) `medication`, `proc_type`, `status`, `route`, `frequency`, `disp_sched`, `infusion_type`, `sliding_scale`, `lockout_interval`, `one_hr_max`, `duration_interval`, `expiration_unit`, `dispensation`, `fill_quantity`
- `poe` (4) `order_type`, `order_subtype`, `transaction_type`, `order_status`
- `poe_detail` (2) `field_name`, `field_value`
- `prescriptions` (12) `drug_type`, `drug`, `formulary_drug_cd`, `gsn`, `ndc`, `prod_strength`, `form_rx`, `dose_val_rx`, `dose_unit_rx`, `form_val_disp`, `form_unit_disp`, `route`
- `services` (2) `prev_service`, `curr_service`
- `transfers` (2) `eventtype`, `careunit`
- `chartevents` (2) `value`, `valueuom`
- `d_items` (6) `label`, `abbreviation`, `linksto`, `category`, `unitname`, `param_type`
- `datetimeevents` (1) `valueuom`
- `icustays` (2) `first_careunit`, `last_careunit`
- `ingredientevents` (3) `amountuom`, `rateuom`, `statusdescription`
- `inputevents` (8) `amountuom`, `rateuom`, `ordercategoryname`, `secondaryordercategoryname`, `ordercomponenttypedescription`, `ordercategorydescription`, `totalamountuom`, `statusdescription`
- `outputevents` (1) `valueuom`
- `procedureevents` (6) `valueuom`, `location`, `locationcategory`, `ordercategoryname`, `ordercategorydescription`, `statusdescription`

## Profiles và điều kiện còn lại

- **HISTORICAL_PILOT** — CoT 5/5 ở cap 8.192. SDE-SQL 5/5 ở grouped 3×3. MAC-SQL 0/5, Ours 0/5. Giữ mười SQL và results đã lưu theo cấu hình gốc của từng lượt lịch sử.
- **SOURCE_ALIGNED_NEXT_RUN** — CoT cap 2.048 chưa chạy. MAC-SQL sửa formatter/parser nhưng strict transport bị chặn. Ours kiểm lại Easy/058 và ghi checkpoint thiếu quyền egress. Gpt-5-mini giữ nguyên ở mọi stage. Hồ sơ MAC/Ours chỉ cập nhật hash cấu hình bằng attestation hiện có. Profile này chưa có predictions để chấm.
- **Ngân sách hiện có** — credit evidence 7.736.289,17 VND, ceiling nghiên cứu 6.962.660,25 VND, dự phòng 773.628,92 VND. Bằng chứng giá và credit còn hiệu lực đến 09:00 ngày 22/11/2026 UTC+7. API caps MAC 25 requests và Ours 120 requests. Caps BigQuery và ledger giữ nguyên.
- **MAC-SQL ở lượt sửa trước** — `temperature=0.1` từng là blocker độc lập với quyền truyền patient-derived column samples. Adapter ở cập nhật đầu báo cáo đã bỏ tham số theo quyết định nghiên cứu mới. Source SQLite error text, metadata BIRD, đối chiếu thứ tự khi đồng hạng và mẫu từ 116 cache bounded vẫn là các chênh lệch cần xử lý trước khi gọi strict. Việc sử dụng mẫu hạn chế cũng cần control cho đúng OpenAI project và Chat Completions.
- **Ours** — schema metadata thông thường và clinical dictionary là hai loại input khác nhau. Bằng chứng còn thiếu là quyền truyền các mục dictionary từ dữ liệu hạn chế và cấu hình data retention của đúng OpenAI project/Responses API, gồm kiểm soát abuse-monitoring, sử dụng huấn luyện và human review. Attestation nội bộ đã được xác nhận còn hiệu lực. [PhysioNet](https://www.physionet.org/news/post/llm-responsible-use/) · [OpenAI Data Controls](https://developers.openai.com/api/docs/guides/your-data)
- **Kiểm thử:** 135 PASS. Đã chạy `paper_sources.py` kiểm tra lại các checkout pinned. Scorer chính thức và dữ liệu benchmark giữ nguyên. Chưa có điểm rubric.
