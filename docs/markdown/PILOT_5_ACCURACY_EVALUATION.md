# Phase C.2 — đánh giá năm câu CLINSQL validation đã lưu

**Trạng thái 14/11/2026:** `OFFICIAL_SCORE_NOT_AVAILABLE`.
Năm câu có SQL thực thi thành công và result artifacts đầy đủ; chưa có bằng
chứng để kết luận câu nào đúng/sai theo **official SQL Score** hoặc
**official Execution Score**. Không gọi lại GPT-5-mini inference, BigQuery,
hoặc official judge trong đợt đánh giá này.

**Quyết định người phụ trách:** quyền sử dụng MIMIC-IV cho nghiên cứu đã được
xử lý, nhưng **chưa phê duyệt truyền result rows tới Azure GPT-5-Chat**.
Không gọi judge, không gửi rows ra ngoài và không gia hạn retention Phase C.1.
Những phần không cần judge tiếp tục độc lập.

## Kiểm tra saved predictions

`scripts/audit_phase_c1_pilot.py` xác minh 5/5 log và artifact: hash,
`complete=true`, row count, job ID, private Windows ACL và các fingerprint
model/schema/index/runtime code. Cả năm dùng `gpt-5-mini-2025-08-07` và
cùng manifest BigQuery. Hai kết quả v4 và ba kết quả v5 khác **SQL budget
approval hash** đã được công bố; không có SQL reservation đang treo. Không
có raw result rows trong application logs. Chi tiết job, token, chi phí và
các lần calibration ở `GPT5_MINI_LIVE_PILOT_RESULTS.md`; audit máy đọc ở
`results/phase_c1_pilot_audit.json`.

## Official CLINSQL scorer — source đã khóa

Source `external/clinsql_official/evaluation/clinical_rubric_scorer.py`
SHA-256 `3a3b9734cab64fafbde7f387d5cb84f569d9072acbb6e7e072311f2b858f475c`
chỉ hỗ trợ **Azure OpenAI `gpt-5-chat`** với API version mặc định
`2024-12-01-preview`, Chat Completions, `temperature=0.2` và tối đa 1024
completion tokens/call. Mỗi lá của SQL rubric và result rubric tạo một
judge request. Năm case hiện có **58 SQL leaves + 52 result leaves = 110
judge requests** theo đúng traversal source; scorer không short-circuit
request dù rubric có sequential/critical weighting. SQL Score và Results
Score là kết quả tổng hợp từ các lá với quy tắc sequential, critical và
weight trong source. `results_score` được báo là Execution Score trong
adapter, nhưng đây là rubric judge score, **không phải cờ SQL chạy thành công**.

Source scorer nạp `result_*.csv` bằng `pandas.read_csv(...).to_dict(orient="records")`
rồi đưa **tất cả model result rows dạng JSON** vào prompt judge. Nếu thư mục
staged có `gold_sql.sql` hoặc `gold_results.csv`, source sẽ thêm reference vào
prompt. Native CLINSQL inference chỉ copy hai rubric JSON, query, predicted
SQL và predicted result CSV; nó **không** copy hai file `gold_*`. Adapter hiện
giữ đúng layout đó; không thêm reference vào judge prompt hoặc sửa scorer.
Staging CSV dùng `DataFrame(...).to_csv(index=False)` như native. Những khác
biệt pandas dtype/NULL/ARRAY/STRUCT cần kiểm chứng trên dữ liệu đại diện trước
scoring hàng loạt; pilot năm case chủ yếu trả scalar, tối đa hai rows.

`scripts/check_official_staging.py` đã staging tạm **5/5** artifacts trong
`results/restricted`, gọi đúng `_load_sample_files` của source scorer và xác
nhận native parser đọc đủ SQL/CSV, cùng row count, không có `gold_*` bổ sung.
Thư mục CSV tạm đã xóa ngay sau kiểm tra; không gọi Azure. Kết quả hash/counts
ở `results/phase_c1_staging_check.json`. Đây là kiểm tra serialization, không
phải scoring.

**Blocker chính thức đã được xác nhận:** policy hiện hành `SEND_RESULTS_TO_LLM=false` và
`PHASE_C1_DATA_HANDLING_POLICY_V5.md` cấm gửi patient results lên LLM;
Phase C.1 approval không bao gồm judge. Môi trường dự án chỉ cấu hình public
OpenAI GPT-5-mini, chưa xác minh Azure GPT-5-Chat endpoint/credentials hoặc
judge budget. Không thể đổi judge sang GPT-5-mini hay bỏ result rows mà vẫn
gọi điểm là official. Cần quyết định có thẩm quyền về truyền kết quả, Azure
judge config và budget 110 calls trước khi chạy. Người phụ trách đã chọn
**chưa cho phép truyền rows** ở giai đoạn này. Credentials phải được cấu
hình cục bộ, không gửi trong chat. Các artifact sẽ hết hạn trong khoảng
20/11/2026 18:52–21/11/2026 00:56 UTC; không kéo dài retention.

## Diagnostic comparison offline — không phải official score

`scripts/evaluate_pilot5_diagnostic.py` đọc **chỉ validation reference CSV**
sau inference, so row counts, column counts và tên cột; khi số cột/hàng tương
thích, nó so multiset không thứ tự, giữ duplicate, phân biệt NULL/NaN/chỗ
trống phía prediction và áp dụng FLOAT tolerance đã chốt. CSV reference có
ô rỗng không chứng minh được nguồn là NULL hay chuỗi rỗng; diagnostic coi ô
rỗng là NULL và phải đánh dấu mơ hồ nếu trường hợp này ảnh hưởng kết luận.
Script chỉ xuất flags/counts và
hash reference, không xuất giá trị bệnh nhân. Máy đọc:
`results/phase_c1_pilot_diagnostic.json`.

- Diagnostic Procedures Easy/058: prediction **1 row × 3 columns**;
  reference **1 × 1**.
- Vital Signs Monitoring Easy/044: prediction **1 × 2**; reference **1 × 1**.
- Laboratory Results Analysis Medium/079: prediction **1 × 5**; reference
  **1 × 8**.
- Medication Management Medium/012: prediction **1 × 8**; reference **1 × 6**.
- Patient Demographics and Admissions Hard/058: prediction **2 × 7**;
  reference **1 × 4**.

**Strict result shape/name match: 0/5.** Vì số cột khác nhau ở cả năm case,
so sánh giá trị theo vị trí không áp dụng; diagnostic không khẳng định tất cả
năm câu sai về lâm sàng. Official rubric có thể cho điểm một phần hoặc khác
strict result equality. Không sửa generated SQL theo reference và không đưa
validation reference vào inference/retrieval.

## Việc còn cần trước official scoring

1. Xác nhận quyền truyền predicted result rows và, nếu source config cần,
   reference/rubric tới Azure GPT-5-Chat; xác định endpoint, vùng dữ liệu,
   retention phía nhà cung cấp và phạm vi phê duyệt. Nếu không hợp lệ, giữ
   `OFFICIAL_SCORE_NOT_AVAILABLE`.
2. Cấu hình Azure GPT-5-Chat tương ứng source và judge budget/ledger riêng,
   tính ít nhất 110 leaf calls cho năm case; khóa source SHA, endpoint/model,
   API version, temperature và failure accounting.
3. Staging chỉ trong thư mục ACL hạn chế, phải có xóa khi artifact gốc hết hạn
   hoặc dùng staging tạm và xóa ngay sau scoring. Không để CSV bệnh nhân trong
   thư mục evaluation không có retention.
4. Chạy scorer trên saved predictions mà không gọi lại inference/BigQuery,
   rồi báo SQL Score, Execution Score từng case và tổng hợp. Giữ diagnostic
   riêng biệt.
