# Dataset hiện tại có phù hợp để so sánh ProbGate không?

Kiểm tra ngày **19/10/2026**. Bằng chứng máy đọc được: `DATASET_AUDIT.json`; script kiểm tra: `tools/audit_dataset_compatibility.py`.

## Kết luận và quyết định

**Phù hợp cho phát triển và kiểm thử nội bộ; không phù hợp để dùng nguyên trạng so điểm với bài ProbGate.**

- **Giữ** MIMIC-IV 3.1 Mini, schema 31 bảng và 180 câu hỏi hiện tại cho ứng dụng, ablation nội bộ, phase tiếng Việt và hội thoại đa lượt.
- **Dùng dataset riêng của ProbGate** cho phần baseline và so sánh nghiên cứu. Bộ này đã nằm trong folder baseline, không cần tải lại hoặc thay database ứng dụng.
- Khi đưa phương pháp của mình vào benchmark, cả baseline và hệ thống của mình phải chạy trên **cùng bộ dữ liệu benchmark**, không phải một bên dùng Mini và một bên dùng demo.
- Việc cần đổi là **nguồn dữ liệu/cấu hình cho thí nghiệm đối chiếu**, không phải xóa dữ liệu đang có hay viết lại toàn bộ hệ thống.

## 1. Dữ liệu ứng dụng hiện tại: đã xác minh được gì?

Đọc trực tiếp `test_dataset.json`, `mimic_examples.json`, `mimic_schema.json`, `config.py`, `build_mimic_mini.py` và README:

- `test_dataset.json`: **180 câu**, có các trường `id`, `question_vi`, `gold_sql`, `tables`, `difficulty`.
- Không có trường `question_en` trong các record đã kiểm tra; đây không phải tập English-input hiện tại.
- Không có `gold_sql` trống hoặc `null`: tập hiện không có nhãn unanswerable theo định dạng EHRSQL. Điều này không chứng minh mọi câu đã được chuyên gia kiểm định là answerable.
- Phân bố difficulty nội bộ: easy 66; medium 60; hard 22; complex 32. Không được coi tên difficulty tự gán là cùng phân bố với benchmark tác giả.
- Có **101 ví dụ few-shot**; **28 ví dụ có SQL canonical trùng một Gold SQL của tập 180 câu**. Collection `sql_examples_eval` hiện có cơ chế loại overlap dạng này; khi đánh giá không dùng nhầm collection gốc hoặc chỉ dựa vào chống trùng chuỗi để bảo đảm hoàn toàn không leakage ngữ nghĩa.
- Schema JSON khai báo **31 bảng**, dùng cột/kiểu SQL theo PostgreSQL và MIMIC-IV gốc.
- Loader mặc định chọn **500 bệnh nhân**, seed mặc định 42, nguồn mặc định thư mục `mimic-iv-3.1`.
- Loader đọc ICD trong gold test/ví dụ để chọn cohort có độ bao phủ. Cách này hữu ích cho bộ test nội bộ, nhưng không phải mẫu benchmark độc lập và không được dùng để dựng lại database cho EHRSQL.

**Giới hạn xác minh:** đã thử kết nối PostgreSQL bằng cấu hình ứng dụng trong transaction read-only nhưng không thành công (`OperationalError`). Vì vậy, 31 bảng và 500 bệnh nhân ở trên là thông tin schema/loader, không phải kết quả kiểm đếm database PostgreSQL đang chạy. Không xác nhận con số hơn 236.000 bản ghi của đề cương là số bản ghi thực tế hiện tại. Không khởi động, xóa hay nạp lại PostgreSQL trong lần kiểm tra này.

## 2. Dataset ProbGate đã chuẩn bị

Đọc đúng database và file snapshot trong folder baseline:

- Database: `upstream/src/data/mimic_iv/mimic_iv.sqlite`, SQLite đã qua preprocessing; **17 bảng**, **94 bệnh nhân**, **308.942 hàng** tính tổng các bảng trong file tác giả.
- Nguồn MIMIC demo thường được mô tả là 100 bệnh nhân; số 94 là đếm thực tế trong file benchmark đã xử lý, không được tự bổ sung bệnh nhân để làm đủ 100.
- Train **5.124 câu**, 450 nhãn unanswerable.
- Dev **1.163 câu**, 232 nhãn unanswerable.
- Test **1.167 câu**, 233 nhãn unanswerable.
- Câu hỏi tiếng Anh, gold SQL và đáp án thực thi theo ID; các split và annotation đã đối chiếu với EHRSQL lịch sử.
- Phiên bản đầu vào `mimic_iv_demo_1.0_*`, source ProbGate `2dcc2230ea049e7fb87160df922933b4ae2645b9`; gold từ EHRSQL `5ddaaa79e6121bf22f808df34166f6f4e03f4c86`.

Đây không phải cùng bộ EHRSQL v1.0.5 đã tìm cho mẫu M3, cũng không phải bản v1.1.2 mới. Giữ nguyên phiên bản theo từng bài, không tráo các annotation giữa chúng.

## 3. Các khác biệt làm phép so sánh trực tiếp không hợp lệ

### Khác cohort và nội dung dữ liệu

Database Mini chọn bệnh nhân từ MIMIC-IV 3.1; benchmark dùng file demo/preprocessing riêng. Cùng một câu hỏi có thể cho số lượng, danh sách ID, ngày hoặc chi phí khác nhau chỉ vì dữ liệu khác, dù SQL đều hợp lý.

Chưa xác minh được số bệnh nhân trùng giữa database PostgreSQL đang chạy và benchmark vì kết nối local thất bại. Không suy đoán số overlap từ tên dataset.

### Khác schema và giá trị mã

- Benchmark có bảng `cost`; schema ứng dụng hiện không có. Câu hỏi về chi phí không thể giữ đúng gold khi chỉ dùng schema hiện tại.
- Benchmark có `admissions.age`; ứng dụng có `patients.anchor_age` và `anchor_year`, không thể coi là cùng cột trực tiếp.
- Benchmark có `patients.dob`; schema ứng dụng mô tả các anchor thay thế.
- Benchmark có `diagnoses_icd.charttime`; schema ứng dụng có `seq_num`, `icd_version` và không có trường đó.
- Benchmark biểu diễn phiên bản ICD trong chuỗi mã; ứng dụng tách `icd_code` và `icd_version`. JOIN và từ điển retrieval phải theo đúng profile.
- Nhiều khác biệt cột khác đã ghi trong `DATASET_AUDIT.json`; không chỉ là đổi PostgreSQL sang SQLite.

### Khác câu hỏi, split và unanswerable

180 câu tiếng Việt nội bộ không phải 1.167 câu tiếng Anh test của bài. Tập nội bộ không có nhãn unanswerable; trong khi từ chối đúng là thành phần được thưởng trong RS. Vì vậy, EX/VSR trên 180 câu không phải RS trên EHRSQL và không thể so số trực tiếp.

### Khác chất lượng nhãn và cách chấm

Unit test bảo đảm Gold SQL phù hợp schema không tự chứng minh mọi Gold SQL đúng ý nghĩa câu hỏi. Không thấy quy trình adjudication độc lập được lưu kèm bộ 180 câu để coi nó tương đương benchmark công bố.

Evaluator nội bộ hiện có quy tắc mẫu số/normalization khác scorer benchmark. Khi thí nghiệm đối chiếu, dùng scorer baseline đã tách, không chỉ đưa 1.167 câu vào evaluator cũ rồi giữ nguyên cách tính EX.

## 4. Có cần đổi dataset không? Áp dụng thế nào?

**Cho thí nghiệm so sánh bài báo: có, cần chuyển sang dataset benchmark cố định. Cho ứng dụng và bộ test nội bộ: không cần thay thế.**

Giữ hai profile:

1. **Profile ứng dụng:** PostgreSQL/MIMIC-IV 3.1 Mini, schema hiện tại, 180 câu tiếng Việt và dữ liệu hội thoại. Báo cáo là thí nghiệm nội bộ.
2. **Profile benchmark:** SQLite 17 bảng của ProbGate, câu hỏi tiếng Anh đúng split, ICD/schema/examples tương thích benchmark. Baseline và phương pháp của mình dùng cùng nguồn dữ liệu này.

Những phần phải thích nghi cho profile benchmark trước khi chạy hệ thống của mình:

- Tạo schema retrieval từ đúng 17 bảng, không dùng fallback DDL 31 bảng.
- Chọn ví dụ RAG từ train, chỉnh model input/output sang tiếng Anh, giữ gold dev/test khỏi inference/few-shot.
- Validator theo schema thực tế; không ép JOIN `icd_version` khi benchmark không có cột này.
- Executor SQLite và clock benchmark, cùng chính sách xử lý lỗi/từ chối.
- Giữ nguyên câu hỏi, dữ liệu, seed/split và gold theo baseline; không chọn lại cohort dựa vào gold test.

Đây là kế hoạch cấu hình riêng, chưa có thay đổi dataset hoặc code ứng dụng nào được thực hiện trong lần kiểm tra này.

## 5. Điểm tác giả cần đối chiếu

Đã thêm toàn bộ **7 dòng dev và 4 dòng test**, đủ RS(0), RS(5), RS(10), RS(N), vào `PAPER.md`. Mốc cấu hình cuối trên **test** là **RS(0) 81.92; RS(5) 78.06; RS(10) 74.21; RS(N) -818.08**.

Nguồn: [ProbGate, Table 1–2](https://aclanthology.org/2024.clinicalnlp-1.65.pdf). Các số này là kết quả công bố, chưa có replay/scoring benchmark trong workspace. Chưa thể tuyên bố phương pháp của mình tốt hơn trước khi chạy cùng giao thức.

## 6. Bước tiếp theo phù hợp

Không cần tải lại dataset. Giữ baseline snapshot, rồi ở giai đoạn chạy: replay 4 nhánh test có cache tác giả và kiểm tra chênh lệch với điểm paper; sau đó mới chạy pipeline của mình trên profile benchmark. Nếu replay chưa khớp, làm rõ nguyên nhân trước khi dùng con số đó làm mốc so sánh.
