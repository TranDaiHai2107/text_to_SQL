# CLINSQL pilot: nguyên nhân 0/5 strict result shape match

**Phạm vi:** 5 câu validation của Phase C.1; đọc saved predictions, question,
diagnostic JSON và validation gold SQL/header **sau inference**. Không đọc hoặc
in raw patient rows; không chạy SQL, model hay judge. Đây là phân tích lỗi,
**không phải official CLINSQL SQL Score/Execution Score**. Tất cả 5 SQL đã thực
thi thành công; strict diagnostic chỉ so cấu trúc kết quả.

| Case | Sai khác và bằng chứng từ SQL đã lưu so với câu hỏi/reference | Nhóm nguyên nhân; ưu tiên |
|---|---|---|
| Diagnostic Procedures Easy/058 | 3 cột `Q1,Q3,IQR` thay vì 1 cột IQR: hai cột thêm là representation. Nhưng prediction đếm distinct `icd_code` theo `hadm_id`, LEFT JOIN gồm cả admission không có thủ thuật, nhận diện MCS bằng regex `long_title`; reference đếm theo `subject_id`, chỉ mã ICD-9 `37.6%`/ICD-10 `5A02%`, không gồm zero. Câu hỏi nói **per hospitalization**, nên reference theo patient cũng không khớp nguyên văn; không thể coi mọi khác biệt với gold là lỗi model. | Projection thừa; cohort/định nghĩa mã và đơn vị aggregation khác reference. **P1**, cần làm rõ benchmark semantics. |
| Vital Signs Easy/044 | Prediction trả median và `admissions_count` (2 so với 1 cột); median có thể vẫn là đáp án được hỏi. Tuy nhiên nhóm `chartevents` theo `hadm_id,subject_id`, trong khi reference nhóm `stay_id` theo ICU stay; itemid lấy bằng tìm label rộng, valuenum chỉ `>0`, còn reference dùng itemid 220052/456 và 40–140. `anchor_age` ở cả hai. | Projection thừa là representation; đơn vị stay, item mapping, range filter là semantic/schema-value grounding. **P1**. “Hospital stay” trong câu hỏi có thể gây mơ hồ so với ICU stay của reference. |
| Laboratory Results Medium/079 | Prediction trả đúng năm phép thống kê được nêu (p25/p50/p75/min/max); reference thêm cohort description, số patient, số admission nên 5 so với 8 cột **không tự chứng minh thiếu đáp án**. Nhưng prediction dùng label `Troponin T` và lọc unit `%ng%`, time window trong admission, mã bệnh qua `long_title`, `anchor_age`; reference dùng itemid 51003, mã ICD cụ thể, tuổi tại admission và không giới hạn charttime theo admission. Các khác biệt có thể đổi cohort/giá trị. | Chủ yếu extra reference metadata; thêm rủi ro semantic do mapping, age/time filters. **P1**. Không có bằng chứng serialization làm mất ba cột. |
| Medication Management Medium/012 | Prediction trả 8 cột, reference 6; có các cột baseline/count phụ. Quan trọng hơn, prediction `glp_by_72h` xét `med_time <= admittime + 72h` và có thể gồm trước admission, trong khi “final 72-hour prevalence” của câu hỏi/reference là **72 giờ trước discharge**. `net_percentage_point_change` của prediction trừ baseline prevalence, reference trừ first-12h initiation. Prediction còn hợp nhất prescriptions/pharmacy/emar và gồm thuốc khác, làm đổi định nghĩa exposure. | **Lỗi semantic/time-window rõ ràng của SQL model**, bên cạnh projection. **P0**. Lượt đầu có lỗi SQL và một refinement; lần sửa cú pháp không kiểm tra semantic. |
| Patient Demographics Hard/058 | Prediction trả 2 hàng theo `readmitted_flag` và 7 cột; câu hỏi/reference yêu cầu một hàng gồm rate, median LOS hai nhóm và percent LOS>6 (4 cột). Hai hàng không chỉ do đổi tên cột; layout không trực tiếp biểu diễn hai median trên cùng một hàng. Prediction dùng `anchor_age`, `edregtime IS NOT NULL`, keyword diagnosis và loại death; reference dùng tuổi tại admission, `admission_location` emergency, ICD chính cụ thể, không loại death. Prediction xét mọi subsequent admission trong 30 ngày; reference dùng `LEAD` next admission. | **Aggregation/projection và cohort/filter semantic**. **P0**. Một phần khác biệt là gold cụ thể hóa “admitted from ED” và mã bệnh không có trong câu chữ. |

## Phân loại nguyên nhân

- **Prompt/model:** Prompt CoT gốc yêu cầu SQL chạy đúng BigQuery, suy luận bảng,
  JOIN, filter, grouping; không cung cấp rubric, ICD/itemid oracle hay output
  contract chi tiết. Model tự suy ra mã/label, age và time window. Trường hợp
  Medication và Hard/058 cho thấy SQL chạy được vẫn có thể sai yêu cầu.
- **Schema context:** Manifest 31 bảng cung cấp tên, kiểu cột và quan hệ, không
  cung cấp ánh xạ clinical concept→ICD/itemid, range MAP hoặc định nghĩa cohort
  trong gold. Không có bằng chứng thiếu bảng/cột hoặc JOIN hỏng ở 5 SQL đã chạy.
- **GoogleSQL adaptation:** Source `build_generation_prompt` và SQL cleaner được
  gọi nguyên bản; adapter chỉ thay hai project literal `physionet-data` thành
  project đã xác minh. Source runner cũng dừng ở SQL thực thi thành công và tối
  đa hai refinement khi execution lỗi. Dry run/guard bổ sung không biến kết quả
  thành SQL khác. Không thấy lỗi dialect là nguyên nhân 0/5 shape mismatch;
  tham số output cap 8192 và model public GPT-5-mini là adaptation đã ghi riêng.
- **Serialization/diagnostic:** 5/5 native CSV loader đọc được saved result;
  prediction column counts đúng số biểu thức SELECT, không có chứng cứ mất cột
  khi lưu. Diagnostic so tên cột rất nghiêm: alias khác hoặc cột thông tin thêm
  cũng bị fail. Vì số cột đều khác, so giá trị theo vị trí không chạy; 0/5 **không
  đồng nghĩa** 0/5 đáp án lâm sàng đúng. CSV NULL/empty và FLOAT tolerance
  chỉ cần điều tra nếu cấu trúc tương thích. Không dùng diagnostic để sửa SQL
  của baseline hoặc tính official score.

## Sửa triển khai và regression không phá fidelity

1. **P0 — giữ CoT baseline nguyên bản.** Không thêm gold-derived projection,
   itemid, ICD code, rubric hay semantic refinement khi SQL đã chạy. Unit test
   `test_successful_extra_projection_does_not_trigger_baseline_refinement`
   khẳng định SQL có cột phụ vẫn kết thúc sau một lần execute, đúng source.
2. **P0 — tách diagnostic khỏi inference.** Tiếp tục lưu SQL/result đầy đủ; so
   schema/alias, cardinality, cohort, age và time windows **chỉ sau inference**
   trên validation. Gắn nhãn `reference_mismatch`, `question_mismatch` hoặc
   `ambiguous`, không gộp thành official score. Không áp dụng bất kỳ sửa SQL nào
   cho năm predictions đã khóa.
3. **P1 — bảo vệ adaptation.** Unit test
   `test_prompt_project_adaptation_changes_only_two_dataset_references`
   kiểm tra prompt synthetic bằng source builder; các parity tests hiện có giữ
   cleaner và hai refinement. Nếu thay đổi schema formatting/transport, kiểm
   tra lại source hash và synthetic SQL serialization trước pilot khác.
4. **P1 — phần hệ thống đề xuất, không phải baseline:** đưa output requirements,
   age-at-admission, per-stay/per-admission và time-window checks vào
   requirement verification bằng metadata/knowledge được phép; kiểm thử trên
   synthetic admissions/medication/stay data. Đây là thay đổi phương pháp Ours
   phải version hóa, không được suy từ gold test.

**Giới hạn:** Không chạy lại năm SQL nên chưa đối chiếu giá trị hay xác nhận
chính xác từng cohort trên BigQuery. Gold validation có chỗ thêm cột/thay đơn
vị so với lời hỏi; cần báo cả hai cách hiểu khi phân tích, không sửa benchmark.
