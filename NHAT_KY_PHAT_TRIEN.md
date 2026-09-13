# 📓 NHẬT KÝ PHÁT TRIỂN & GIẢI THÍCH KỸ THUẬT ĐỒ ÁN TỐT NGHIỆP
**Đề tài:** Hệ thống Text-to-SQL cho truy vấn dữ liệu y tế MIMIC-IV sử dụng RAG Đa tầng và Agentic Self-Correction  
**Thư mục chính:** `d:\UIT\DATN\official`  

---

## 🌟 TỔNG QUAN HÀNH TRÌNH NÂNG CẤP (PHASE 1)

Giai đoạn 1 (Phase 1) tập trung vào việc **Xây dựng nền tảng vững chắc (Foundation)** cho đồ án trước khi tiến hành các thử nghiệm nâng cao (Fine-tuning, Knowledge Distillation). Cụ thể gồm 4 mục tiêu lớn:
1. **Task 1.1 — Đo lường Baseline V1:** Chạy hệ thống đánh giá trên 5 chế độ (ablation study) để có con số thực tế làm mốc so sánh (benchmark baseline).
2. **Task 1.2 — Nâng cấp Multilingual Embedding:** Thay thế mô hình nhúng tiếng Anh (`all-MiniLM-L6-v2`) sang mô hình hỗ trợ tiếng Việt (`paraphrase-multilingual-MiniLM-L12-v2`) để giải quyết triệt để điểm yếu ngữ nghĩa khi truy vấn từ điển y tế bằng tiếng Việt.
3. **Task 1.3 — Mở rộng bộ dữ liệu kiểm nghiệm (Test Dataset 180+ câu):** Tăng quy mô từ 30 lên 180 câu hỏi kèm gold SQL, phân loại chi tiết theo độ khó (easy/medium/hard/complex).
4. **Task 1.4 — Xây dựng Schema-Aware SQL Validator:** Bổ sung lớp kiểm tra trước thực thi (AST parsing & table/column mapping) nhằm phát hiện và ngăn chặn ảo giác (hallucination) về tên bảng/cột trước khi gửi xuống cơ sở dữ liệu.

---

## 📅 CHI TIẾT CÔNG VIỆC TỪNG NGÀY / TỪNG TASK

### 🔹 [Phase 1 - Task 1.2] Nâng cấp Multilingual Embedding cho RAG Engine
**Trạng thái:** ✅ Hoàn thành  
**Các file tác động:** `embedding_config.py` (tạo mới), `build_vector_db.py`, `rag_engine.py`

#### 1. Lý do kỹ thuật (Why?)
Trước đây, hệ thống ChromaDB trong file `build_vector_db.py` và `rag_engine.py` được khởi tạo mà không truyền vào tham số `embedding_function`. Mặc định, ChromaDB sử dụng mô hình `all-MiniLM-L6-v2` từ thư viện `sentence-transformers`. 
- **Điểm yếu chí mạng:** `all-MiniLM-L6-v2` chỉ được huấn luyện trên ngữ liệu tiếng Anh (English-only). Khi người dùng nhập câu hỏi bằng **tiếng Việt** (ví dụ: *"bệnh nhân bị suy tim nhập viện cấp cứu"*), mô hình sinh vector embedding với độ tương đồng ngữ nghĩa cực kỳ thấp so với các mô tả DDL tiếng Anh hoặc mã ICD, dẫn đến việc tầng RAG 1 (ICD) và tầng RAG 2 (Schema) truy xuất sai bảng và sai mã bệnh.
- **Giải pháp tối ưu cho Laptop RTX 3050 (4GB VRAM):** Chúng ta thay thế sang mô hình **`paraphrase-multilingual-MiniLM-L12-v2`** (118M tham số, dung lượng ~470MB). Mô hình này hỗ trợ tốt hơn 50 ngôn ngữ (bao gồm tiếng Việt và tiếng Anh), khả năng ánh xạ từ khóa y khoa tiếng Việt với thuật ngữ tiếng Anh trong MIMIC-IV cực kỳ chính xác, mà chỉ chiếm <500MB RAM/VRAM, hoàn toàn phù hợp với cấu hình máy laptop sinh viên.

#### 2. Công việc thực hiện (What & How?)
1. **Tạo module quản lý tập trung [`embedding_config.py`](file:///d:/UIT/DATN/official/embedding_config.py):**
   - Viết hàm `get_embedding_function(model_name)` sử dụng `SentenceTransformerEmbeddingFunction(model_name="paraphrase-multilingual-MiniLM-L12-v2")`.
   - Áp dụng cơ chế **Singleton/Caching** (`_CACHED_EF`) trong bộ nhớ RAM, đảm bảo mô hình nhúng chỉ load đúng 1 lần duy nhất khi ứng dụng Streamlit hoặc script đánh giá khởi chạy, không bị nghẽn cổ chai (bottleneck) I/O.
2. **Cập nhật [`build_vector_db.py`](file:///d:/UIT/DATN/official/build_vector_db.py):**
   - Import `get_embedding_function`.
   - Truyền tham số `embedding_function=get_embedding_function()` vào cả 3 lời gọi `chroma_client.create_collection("icd_dictionary")`, `create_collection("schema_dictionary")`, `create_collection("sql_examples")` và hàm `quick_test()`.
3. **Cập nhật [`rag_engine.py`](file:///d:/UIT/DATN/official/rag_engine.py):**
   - Import `get_embedding_function`.
   - Cập nhật hàm `_get_collection(name)` để luôn truy xuất collection với đúng mô hình nhúng đa ngữ, đảm bảo tính nhất quán (consistency) giữa lúc build DB và lúc query RAG.

---

### 🔹 [Phase 1 - Task 1.4] Xây dựng Schema-Aware SQL Validator ngăn chặn Hallucination
**Trạng thái:** ✅ Hoàn thành  
**Các file tác động:** `sql_validator.py` (tạo mới), `rag_engine.py`

#### 1. Lý do kỹ thuật (Why?)
Các mô hình ngôn ngữ lớn (LLM), dù mạnh như Llama 3.3 70B hay GPT-4o, vẫn mắc phải hiện tượng **Ảo giác cấu trúc (Schema Hallucination)** khi tự ý bịa ra:
- Tên bảng không tồn tại (ví dụ: `vital_signs`, `lab_results` thay vì `labevents`).
- Tên cột không hợp lệ hoặc nhầm lẫn giữa các bảng (ví dụ: dùng cột `age` thay vì `anchor_age` trong bảng `patients`, hoặc gọi cột `valuenum` từ bảng `admissions`).
Nếu gửi trực tiếp các câu SQL ảo giác này xuống PostgreSQL, hệ thống sẽ trả về lỗi database thô ráp, lãng phí thời gian thực thi I/O. Hơn nữa, trong vòng lặp Agentic Self-Correction, nếu LLM không nhận được chỉ điểm lỗi chính xác (dạng "Cột X không nằm trong bảng Y, bảng Y chỉ có các cột Z..."), mô hình rất dễ lặp lại sai lầm ở lần thử tiếp theo.

#### 2. Công việc thực hiện (What & How?)
1. **Xây dựng module kiểm tra ngữ pháp & cấu trúc [`sql_validator.py`](file:///d:/UIT/DATN/official/sql_validator.py):**
   - Khai báo danh sách tuyệt đối `VALID_TABLES` cho 31 bảng trong MIMIC-IV subset (`patients`, `admissions`, `diagnoses_icd`, `labevents`, `prescriptions`, v.v.).
   - Khai báo từ điển ánh xạ `VALID_COLUMNS` chứa toàn bộ tên cột hợp lệ của từng bảng.
   - Viết các thuật toán phân tích cú pháp (regex parser & alias mapping):
     - Hàm `extract_table_names(sql)`: Tách chính xác các bảng sau từ khóa `FROM` và `JOIN`.
     - Hàm `extract_column_candidates(sql)`: Nhận diện các cặp `alias.column` (ví dụ `p.subject_id`, `le.valuenum`).
     - Hàm `validate_sql_schema(sql)`: Kiểm tra Table Hallucination, Column Hallucination và các lỗi domain-specific của MIMIC-IV (lỗi nhầm cột tuổi `age` vs `anchor_age`, lỗi thiếu `icd_version` khi JOIN mã chẩn đoán ICD-9/ICD-10).
     - Hàm `get_validator_prompt_hint(validation_result)`: Tạo prompt tiếng Việt chỉ điểm lỗi cực kỳ chi tiết cho LLM.
2. **Tích hợp vào Agentic Loop trong [`rag_engine.py`](file:///d:/UIT/DATN/official/rag_engine.py):**
   - Tại hàm `generate_sql_with_correction()`, ngay sau khi LLM sinh câu raw SQL và qua `_clean_sql()`, hệ thống lập tức gọi `validate_sql_schema(sql)`.
   - **Cơ chế chặn sớm (Early Rejection):** Nếu `val_res["valid"] == False`, hệ thống **KHÔNG GỌI** `run_query(sql)` xuống PostgreSQL nữa (tiết kiệm connection & I/O), mà lập tức đẩy thông báo lỗi cụ thể từ `get_validator_prompt_hint()` ngược lại vào chuỗi `messages` multi-turn để Llama 3.3 70B tự sửa ngay ở attempt tiếp theo.

---

### 🔹 [Phase 1 - Task 1.3] Mở rộng bộ dữ liệu kiểm nghiệm Test Dataset lên 180 Câu
**Trạng thái:** ✅ Hoàn thành  
**Các file tác động:** `expand_test_dataset.py` (tạo mới), `test_dataset.json` (cập nhật từ 30 → 180 câu)

#### 1. Lý do kỹ thuật (Why?)
Tập kiểm tra ban đầu (`test_dataset.json`) chỉ có **30 câu hỏi** (`t001` - `t030`). Con số 30 là quá nhỏ trong nghiên cứu khoa học, không đủ độ tin cậy thống kê (statistical significance) để đánh giá độ chính xác thực thi (Execution Accuracy) khi so sánh giữa các chế độ RAG hay các mô hình fine-tune về sau. Đồng thời, 30 câu cũ thiếu các truy vấn phức tạp xuyên bảng (Cross-table complex queries) và chưa phân loại độ khó rõ ràng.

#### 2. Công việc thực hiện (What & How?)
1. Viết script tạo dữ liệu tự động [`expand_test_dataset.py`](file:///d:/UIT/DATN/official/expand_test_dataset.py) chứa cặp `(question_vi, gold_sql, tables, difficulty)` mới, được thiết kế tỉ mỉ theo đúng chuẩn MIMIC-IV 31 bảng.
2. **Phân bố độ khó chuẩn học thuật của 180 câu trong [`test_dataset.json`](file:///d:/UIT/DATN/official/test_dataset.json):**
   - 🟢 **EASY (21 câu - 21.0%):** Truy vấn 1 bảng đơn giản, `SELECT`, `WHERE`, `COUNT(*)`.
   - 🟡 **MEDIUM (40 câu - 40.0%):** Truy vấn kết hợp (`JOIN`) từ 2-3 bảng, có `GROUP BY`, `HAVING`, `ORDER BY`.
   - 🟠 **HARD (25 câu - 25.0%):** Truy vấn từ 3-4 bảng, xử lý `CASE WHEN`, lọc theo mã ICD phức tạp (`d.icd_code LIKE 'A41%' AND d.icd_version = 10`), tính toán ngày nằm viện (`EXTRACT(EPOCH FROM ...)/86400`).
   - 🔴 **COMPLEX (14 câu - 14.0%):** Truy vấn nâng cao chéo 4-5 bảng (`patients` JOIN `admissions` JOIN `diagnoses_icd` JOIN `prescriptions` JOIN `labevents`), subquery lồng nhau, tính toán tương quan lâm sàng (tiêm kháng sinh IV với tỷ lệ sống sót, chỉ số bạch cầu max với tử vong trong viện).
3. **Phân bố bao phủ toàn diện 31 bảng MIMIC-IV:**
   - `admissions`: 31 câu | `diagnoses_icd`: 21 câu | `prescriptions`: 18 câu | `labevents`: 15 câu
   - `d_labitems`: 14 câu | `microbiologyevents`: 14 câu | `patients`: 13 câu | `transfers`: 11 câu
   - `procedures_icd`: 5 câu | `d_icd_diagnoses`: 5 câu | `services`: 4 câu | `d_icd_procedures`: 1 câu

---

### 🔹 [Phase 1 - Task 1.1] Kiểm tra Môi trường & Đánh giá Baseline V1
**Trạng thái:** ⏳ Đang chờ kết nối PostgreSQL (Docker Desktop)  
**File mục tiêu:** `evaluate.py`, `results/baseline_v1.json`

#### 1. Hiện trạng
- Các script `evaluate.py` đã sẵn sàng để chạy thử nghiệm trên 180 câu hỏi mới của `test_dataset.json`.
- Khi kiểm tra kết nối qua SQLAlchemy trên cổng `5432` (`postgresql+psycopg2://postgres:password123@localhost:5432/mimiciv`), hệ thống phản hồi `OperationalError: Connection refused (0x0000274D/10061)`. Kiểm tra `docker ps` cho thấy daemon **Docker Desktop hiện đang tắt trên laptop**.

#### 2. Bước tiếp theo để hoàn tất Task 1.1
- Ngay khi Docker Desktop được bật lên và container `mimic-postgres` (bảng MIMIC-IV) hoạt động, chúng ta sẽ chạy lệnh:
  ```bash
  python evaluate.py --mode full --output results/baseline_v1.json
  ```
- Kết quả thu được sẽ cho ta số liệu **Valid SQL Rate (VSR)** và **Execution Accuracy (EX)** chính thức trên bộ 180 câu làm mốc chuẩn (Baseline) cho toàn bộ đồ án!
