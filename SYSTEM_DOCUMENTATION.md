# Tài liệu Hệ thống Kỹ thuật: MIMIC-IV Text-to-SQL Đa Tầng Khép Kín (Closed-Loop Clinical Text-to-SQL)

**Đồ án Tốt nghiệp – Khoa Công nghệ Thông tin, Trường Đại học Công nghệ Thông tin (UIT)**  
**Chủ đề:** Hệ thống chuyển đổi câu hỏi y khoa tiếng Việt sang SQL hai chiều kết hợp Retrieval-Augmented Generation (RAG 3 tầng), Schema-Aware Validator, Agentic Self-Correction và Diễn giải kết quả lâm sàng trên cơ sở dữ liệu MIMIC-IV.

---

## Mục lục

1. [Tổng quan hệ thống](#1-tổng-quan-hệ-thống)
2. [Kiến trúc tổng thể và luồng xử lý](#2-kiến-trúc-tổng-thể-và-luồng-xử-lý)
3. [Công nghệ và mô hình sử dụng](#3-công-nghệ-và-mô-hình-sử-dụng)
4. [Dữ liệu: MIMIC-IV lâm sàng](#4-dữ-liệu-mimic-iv-lâm-sàng)
5. [Cơ sở Tri thức Vector (Knowledge Base RAG)](#5-cơ-sở-tri-thức-vector-knowledge-base-rag)
6. [Các tính năng nâng cao cốt lõi](#6-các-tính-năng-nâng-cao-cốt-lõi)
7. [Bộ dữ liệu kiểm thử và Phương pháp đánh giá](#7-bộ-dữ-liệu-kiểm-thử-và-phương-pháp-đánh-giá)
8. [Tính mới khoa học và Đóng góp của Đề tài](#8-tính-mới-khoa-học-và-đóng-góp-của-đề-tài)
9. [Cấu trúc thư mục mã nguồn](#9-cấu-trúc-thư-mục-mã-nguồn)
10. [Hướng dẫn cài đặt và vận hành](#10-hướng-dẫn-cài-đặt-và-vận-hành)

---

## 1. Tổng quan hệ thống

### 1.1. Bài toán thực tế
Tại các cơ sở y tế và bệnh viện, dữ liệu lâm sàng lưu trữ trong cơ sở dữ liệu quan hệ (RDBMS) thường có cấu trúc đồ sộ, nhiều ràng buộc nghiệp vụ và hàng trăm mã chẩn đoán quốc tế (ICD-9/ICD-10). Y bác sĩ và nhà nghiên cứu lâm sàng gặp rào cản lớn do không có chuyên môn lập trình SQL để truy vấn trực tiếp.

### 1.2. Thách thức kỹ thuật đặc thù
- **Bất đồng ngôn ngữ (Cross-lingual Gap):** Câu hỏi bằng tiếng Việt nhưng cấu trúc cơ sở dữ liệu và mã ICD định nghĩa bằng tiếng Anh.
- **Rộng lớn và loãng ngữ cảnh (Schema Hallucination):** MIMIC-IV có hàng chục bảng, việc đưa toàn bộ DDL vào prompt gây nhiễu, làm LLM dễ bịa ra tên bảng hoặc tên cột không có thực.
- **Tính toán lâm sàng đặc thù:** Tính toán thời gian nằm viện (Length of Stay - LOS), lọc điều kiện phiên bản ICD kép (`icd_code` VÀ `icd_version`), ép kiểu dữ liệu timestamp.
- **Ngữ cảnh hội thoại đa lượt phức tạp:** Đại từ tỉnh lược ("trong số đó", "bao nhiêu người") yêu cầu hệ thống phải hiểu được cả câu SQL và tập dữ liệu kết quả trước đó.
- **Rào cản đầu ra kỹ thuật:** Bác sĩ cần một câu trả lời súc tích bằng ngôn ngữ tự nhiên thay vì chỉ nhận một bảng dữ liệu thô.

### 1.3. Giải pháp Đề xuất
Xây dựng pipeline **Closed-Loop Bidirectional Text-to-SQL**:
1. **Chiều xuôi (Text-to-SQL):** Tiếng Việt → Rewrite đa lượt → RAG 3 tầng (ICD + Schema + Examples) → LLM → Schema-Aware Validator → Agentic Self-Correction → Chạy trên PostgreSQL.
2. **Chiều ngược (SQL-to-Text):** Bảng kết quả DataFrame → LLM Diễn giải lâm sàng → Câu trả lời ngôn ngữ tự nhiên tiếng Việt cho y bác sĩ.

---

## 2. Kiến trúc tổng thể và luồng xử lý

```
                    NGƯỜI DÙNG (Bác sĩ / Nhà nghiên cứu)
                    "Trong số đó, có bao nhiêu người nam?"
                                     │
 ════════════════════════════════════╪══════════════════════════════════════════════
  MODULE 1: MULTI-TURN QUERY REWRITING (Context-Aware)
 ════════════════════════════════════╪══════════════════════════════════════════════
                                     ▼
   Đọc: Câu hỏi trước + SQL trước + Kết quả trước
   → Viết lại thành câu độc lập: "Trong số bệnh nhân nữ, có bao nhiêu bệnh nhân nam?"
                                     │
 ════════════════════════════════════╪══════════════════════════════════════════════
  MODULE 2: RETRIEVAL-AUGMENTED GENERATION (RAG 3 TẦNG)
 ════════════════════════════════════╪══════════════════════════════════════════════
                                     ▼
   ┌───────────────────┐    ┌───────────────────┐    ┌───────────────────┐
   │  [RAG Tầng 1]     │    │  [RAG Tầng 2]     │    │  [RAG Tầng 3]     │
   │  ICD Dictionary   │    │  Schema Selection │    │  SQL Few-Shot     │
   │  ChromaDB         │    │  ChromaDB         │    │  ChromaDB         │
   │  10,000 mã bệnh   │    │  12 bảng MIMIC    │    │  40 cặp Gold Q-SQL│
   │  → ICD-9, ICD-10  │    │  → 3-5 bảng + DDL │    │  → 3 mẫu tương tự │
   └─────────┬─────────┘    └─────────┬─────────┘    └─────────┬─────────┘
             └────────────────────────┼────────────────────────┘
                                      │
 ═════════════════════════════════════╪════════════════════════════════════════════
  MODULE 3: PROMPT COMPOSER & LLM GENERATION
 ═════════════════════════════════════╪════════════════════════════════════════════
                                      ▼
   Ghép System Prompt (chứa Subquery Rule 8) + ICD + Schema DDL + Examples + Q
   → Gọi Groq LPU API (Qwen 2.5 27B / Llama 3.3 70B, max_tokens=900)
   → Sinh câu lệnh SQL ứng viên
                                      │
 ═════════════════════════════════════╪════════════════════════════════════════════
  MODULE 4: SCHEMA-AWARE SQL VALIDATOR (sql_validator.py)
 ═════════════════════════════════════╪════════════════════════════════════════════
                                      ▼
   Kiểm tra tĩnh AST: Bảng tồn tại? Cột đúng bảng? JOIN đủ icd_version?
     ├── Hợp lệ (Valid) ────────────────────────┐
     └── Không hợp lệ (Invalid) ────────────┐   │
                                            │   │
 ═══════════════════════════════════════════╪═══╪══════════════════════════════════
  MODULE 5: AGENTIC SELF-CORRECTION & EXECUTION │
 ═══════════════════════════════════════════╪═══╪══════════════════════════════════
                                            ▼   │
   Phản hồi prompt lỗi cho LLM tự sửa ◄─────┘   │
   (Tối đa 2 lần retry)                         │
                                                │
   Thực thi SQL trên PostgreSQL (MIMIC-IV) ◄────┘
     ├── Thành công: Thu được DataFrame kết quả
     └── Runtime error: Thu thập traceback gửi lại LLM sửa
                                     │
 ════════════════════════════════════╪══════════════════════════════════════════════
  MODULE 6: RESULT INTERPRETATION (SQL-to-Text)
 ════════════════════════════════════╪══════════════════════════════════════════════
                                     ▼
   interpret_result(question, sql, df):
   Tổng hợp bảng số liệu thành câu trả lời ngôn ngữ tự nhiên tiếng Việt:
   💬 "Trong nhóm bệnh nhân nữ được khảo sát, không có bệnh nhân nam nào (0 ca)."
   + Bảng dữ liệu tương tác + Tự động vẽ biểu đồ + Xuất CSV trên Streamlit UI
```

---

## 3. Công nghệ và mô hình sử dụng

### 3.1. Mô hình Ngôn ngữ Lớn (LLM)
- **Mô hình chính:** `qwen/qwen3.8-27b` (hỗ trợ linh hoạt chuyển đổi sang `llama-3.3-70b-versatile`) phục vụ qua hạ tầng siêu tốc **Groq LPU**.
- **Cấu hình suy luận (Inference Settings):**
  - `temperature = 0`: Đảm bảo tính xác định (deterministic) tối đa cho mã SQL.
  - `max_tokens = 900` (khi sinh SQL) và `max_tokens = 256` (khi viết lại câu hỏi): Được tính toán chuẩn xác để không bao giờ vượt ngưỡng trần **1,000 Output Tokens Per Minute (OTPM)** của Groq Free Tier, loại bỏ hoàn toàn lỗi `429 RateLimitError`.

### 3.2. Mô hình Nhúng Đa Ngôn Ngữ (Multilingual Embedding)
- **Mô hình:** `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2`.
- **Đặc tính:** Hỗ trợ hơn 50 ngôn ngữ (bao gồm tiếng Việt và tiếng Anh), kích thước nhỏ gọn (~470MB, dimension 384), chạy mượt mà trên CPU/GPU phổ thông.
- **Vai trò:** Cầu nối ngữ nghĩa giữa câu hỏi triệu chứng bệnh tiếng Việt và mã danh mục ICD tiếng Anh.

### 3.3. Cơ sở Dữ liệu & Vector Store
- **Vector Database:** ChromaDB (`PersistentClient`), lưu trữ cục bộ tại `./mimic_chroma_db/`.
- **Cơ sở dữ liệu quan hệ:** PostgreSQL 15 chạy containerized trong Docker (`mimic-postgres`), kết nối qua SQLAlchemy và `psycopg2`.

### 3.4. Giao diện Người dùng
- **Streamlit Framework:** Giao diện Web tương tác thời gian thực, hỗ trợ:
  - Hiển thị trực quan các Tag RAG (`ICD`, `SCHEMA`, `EXAMPLES`, `REWRITE`, `FIX`).
  - Khung màu tím gradient nổi bật câu trả lời tự nhiên của mô-đun SQL-to-Text.
  - Tự động nhận diện kiểu dữ liệu để sinh biểu đồ (Bar Chart).
  - Tích hợp bảng thống kê và biểu đồ cột kết quả Ablation Study tự động.

---

## 4. Dữ liệu: MIMIC-IV lâm sàng

Hệ thống sử dụng tập con đại diện **MIMIC-IV v3.1 Mini** gồm 500 bệnh nhân ngẫu nhiên có đầy đủ hồ sơ bệnh án:

| Tên bảng | Số dòng | Nội dung lưu trữ |
|---|---|---|
| `patients` | 500 | Thông tin nhân khẩu học, giới tính, tuổi mốc |
| `admissions` | ~777 | Các đợt nhập viện, loại hình nhập viện, cờ tử vong trong viện |
| `diagnoses_icd` | ~8,582 | Chẩn đoán mã ICD gắn liền từng đợt nhập viện |
| `d_icd_diagnoses` | 112,107 | Danh mục tra cứu tên bệnh ICD-9 và ICD-10 đầy đủ |
| `procedures_icd` | ~1,270 | Các thủ thuật / phẫu thuật đã thực hiện |
| `d_icd_procedures` | 86,423 | Danh mục tra cứu thủ thuật y tế đầy đủ |
| `labevents` | ~175,051 | Kết quả xét nghiệm sinh hóa / huyết học (Top 50 chỉ số) |
| `d_labitems` | 1,650 | Danh mục tra cứu tên xét nghiệm |
| `prescriptions` | ~26,489 | Đơn thuốc, liều lượng, đường dùng |
| `transfers` | ~3,309 | Lịch sử chuyển khoa, chuyển buồng bệnh |
| `services` | ~845 | Dịch vụ lâm sàng phụ trách |
| `microbiologyevents` | ~5,487 | Kết quả cấy vi sinh vật và kháng sinh đồ |

---

## 5. Cơ sở Tri thức Vector (Knowledge Base RAG)

ChromaDB quản lý 3 collection chuyên biệt:

1. **`icd_dictionary` (10,000 vectors):**
   - Chứa 6,000 mã ICD-10 và 4,000 mã ICD-9 phổ biến nhất kèm tên bệnh tiếng Anh.
   - Metadata: `icd_code`, `icd_version`.
   - Giúp ánh xạ chuẩn: *"viêm phổi"* → ICD-9 `486`, ICD-10 `J189`.

2. **`schema_dictionary` (12 vectors):**
   - Chứa mô tả song ngữ (Việt - Anh) và câu lệnh DDL `CREATE TABLE` của 12 bảng.
   - Metadata: `table`, `description_vi`, `ddl`.
   - Giúp LLM chỉ nhận DDL của các bảng cần thiết (ví dụ: chỉ lấy `patients` và `admissions` thay vì cả 12 bảng).

3. **`sql_examples` (40 vectors):**
   - Chứa 40 cặp câu hỏi tiếng Việt ↔ SQL Gold phân loại theo 7 nhóm pattern phức tạp (đếm, JOIN ICD, aggregate, mortality, LOS, lab filter, subquery).
   - Truy xuất 3 ví dụ tương đồng nhất làm gợi ý few-shot trong prompt.

---

## 6. Các tính năng nâng cao cốt lõi

### 6.1. Schema-Aware SQL Validator (`sql_validator.py`)
Màng lọc bảo vệ trước thực thi:
- Phân tích cây cú pháp Abstract Syntax Tree (AST).
- So sánh các bảng và cột được dùng trong SQL với lược đồ thực tế trong `mimic_schema.json`.
- Bắt buộc kiểm tra điều kiện JOIN bảng ICD: phải khớp cả `icd_code` VÀ `icd_version`.
- Nếu phát hiện lỗi ảo giác, hệ thống sinh thông báo chi tiết trả về LLM để sửa trước khi lệnh chạm tới database.

### 6.2. Vòng lặp Tự Sửa Lỗi Tác tử (Agentic Self-Correction)
- Hàm `generate_sql_with_correction()` triển khai mô hình Agentic: **Reasoning → Execution → Observation → Adjustment**.
- Cho phép tối đa 2 lần retry nếu SQL bị lỗi cú pháp hoặc runtime exception.
- Lịch sử sửa lỗi được ghi nhận đầy đủ và trực quan hóa từng bước trên giao diện người dùng.

### 6.3. Xử lý Ngữ cảnh Đa lượt Kế thừa Sâu (Context-Aware Multi-turn)
- Hàm `rewrite_question()` được cấp quyền đọc cả lịch sử câu hỏi, câu SQL và tóm tắt bảng dữ liệu của các lượt tương tác trước.
- **Cơ chế Subquery/CTE Rule 8:** Hướng dẫn LLM sinh câu truy vấn tập con khi người dùng đặt câu hỏi phụ thuộc (ví dụ: *"trong đó có bao nhiêu nam?"* sau khi hỏi về nhóm nữ):
  ```sql
  SELECT COUNT(*) FROM patients 
  WHERE gender = 'M' 
    AND subject_id IN (SELECT subject_id FROM patients WHERE gender = 'F' LIMIT 6);
  -- Kết quả: 0 (chuẩn xác về mặt logic và dữ liệu)
  ```

### 6.4. Diễn giải Kết quả Hai chiều (SQL-to-Text Interpretation)
- Hàm `interpret_result()` tiếp nhận câu hỏi gốc, câu SQL và DataFrame kết quả.
- Sử dụng prompt chuyên biệt cho trợ lý y tế: Tóm tắt số liệu định lượng, chỉ ra xu hướng nổi bật, thông báo rõ ràng khi kết quả rỗng và loại bỏ các thuật ngữ kỹ thuật database phức tạp để trả về câu trả lời tự nhiên, thân thiện cho bác sĩ.

---

## 7. Bộ dữ liệu kiểm thử và Phương pháp đánh giá

### 7.1. Tập kiểm thử chuẩn hóa 100 câu (`test_dataset.json`)
Bộ dữ liệu gồm 100 câu hỏi tiếng Việt độc lập kèm Gold SQL chuẩn, không trùng lặp với tập few-shot:
- **Easy (21%):** Truy vấn đơn bảng, đếm số lượng, lọc thuộc tính cơ bản.
- **Medium (40%):** JOIN 2–3 bảng, lọc theo mã bệnh ICD, tính tỷ lệ phần trăm.
- **Hard (25%):** JOIN nhiều bảng, tính khoảng thời gian (LOS), lọc giá trị xét nghiệm định lượng.
- **Complex (14%):** Lồng ghép Subquery, CTE, phân tích điều trị đa tầng.

### 7.2. Các chỉ số đo lường (Metrics)
1. **Valid SQL Rate (VSR):**
   $$\text{VSR} = \frac{\text{Số câu SQL thực thi không lỗi}}{\text{Tổng số câu hỏi}} \times 100\%$$
2. **Execution Accuracy (EX):**
   $$\text{EX} = \frac{\text{Số câu SQL có kết quả khớp tuyệt đối với Gold SQL}}{\text{Số câu có Gold SQL hợp lệ}} \times 100\%$$
   *(So sánh dựa trên frozenset chuẩn hóa các dòng dữ liệu để không phụ thuộc vào thứ tự cột hoặc thứ tự sắp xếp dòng).*
3. **Average Latency (s):** Thời gian phản hồi trung bình từ lúc nhận câu hỏi đến khi trả kết quả.

### 7.3. Thiết kế Ablation Study (5 chế độ)
Script `evaluate.py` hỗ trợ đo lường độc lập trên 5 mode:
- `base`: Baseline LLM thuần túy, không dùng RAG.
- `icd`: Chỉ kích hoạt RAG tra cứu mã ICD.
- `schema`: Chỉ kích hoạt RAG chọn bảng Schema.
- `examples`: Chỉ kích hoạt RAG Few-shot Examples.
- `full`: Toàn bộ hệ thống đề xuất (3 tầng RAG + Validator + Self-Correction).

---

## 8. Tính mới khoa học và Đóng góp của Đề tài

1. **Đóng góp 1 (Ngôn ngữ):** Hệ thống Text-to-SQL đầu tiên trên dữ liệu lâm sàng MIMIC-IV tối ưu hóa cho câu hỏi tiếng Việt bằng mô hình nhúng đa ngôn ngữ.
2. **Đóng góp 2 (Kiến trúc RAG):** Phân rã tri thức miền y tế thành 3 tầng RAG độc lập thay vì RAG 1 tầng truyền thống.
3. **Đóng góp 3 (Độ tin cậy):** Tích hợp màng lọc Schema-Aware AST Validator kết hợp vòng lặp Agentic Self-Correction triệt tiêu hallucination.
4. **Đóng góp 4 (Hội thoại sâu):** Giải quyết bài toán hội thoại đa lượt lâm sàng với cơ chế sinh Subquery tập con chính xác.
5. **Đóng góp 5 (Hệ thống khép kín):** Xây dựng hoàn chỉnh luồng hai chiều Text-to-SQL và SQL-to-Text mang giá trị ứng dụng thực tiễn cao cho bệnh viện.

---

## 9. Cấu trúc thư mục mã nguồn

```
d:\Github\text_to_SQL\
├── build_mimic_mini.py       # Script trích xuất và nạp dữ liệu MIMIC-IV vào PostgreSQL
├── build_vector_db.py        # Script tạo 3 collection ChromaDB
├── embedding_config.py       # Cấu hình mô hình nhúng đa ngữ multilingual
├── sql_validator.py          # Module Schema-Aware SQL Validator (AST)
├── rag_engine.py             # Lõi hệ thống: RAG 3 tầng, LLM, Self-Correction, Rewrite, Interpretation
├── app.py                    # Ứng dụng Web Chatbot thông minh trên Streamlit
├── evaluate.py               # Script đo lường thực nghiệm Ablation Study tự động
├── expand_test_dataset.py    # Script khởi tạo bộ test 100 câu hỏi chuẩn hóa
├── mimic_schema.json         # Lược đồ DDL và mô tả song ngữ 12 bảng MIMIC-IV
├── mimic_examples.json       # 40 cặp Gold Q-SQL cho tầng Few-shot RAG
├── test_dataset.json         # 100 câu hỏi test phân tầng kèm Gold SQL
├── evaluate_results.json     # File lưu kết quả thực nghiệm VSR và EX
├── DE_TAI_CHINH_THUC.md      # Đề cương thuyết minh đồ án tốt nghiệp chính thức
├── TONG_HOP_DU_AN.md         # Báo cáo tổng hợp tiến độ và giải thích đề tài
├── HUONG_DAN_CHAY.md         # Hướng dẫn chi tiết cài đặt và vận hành hệ thống
└── SYSTEM_DOCUMENTATION.md   # Tài liệu kiến trúc kỹ thuật hệ thống (Tài liệu này)
```

---

## 10. Hướng dẫn cài đặt và vận hành

Xem hướng dẫn chi tiết từng bước tại [HUONG_DAN_CHAY.md](file:///d:/Github/text_to_SQL/HUONG_DAN_CHAY.md).

**Lệnh khởi chạy nhanh:**
```bash
# 1. Bật cơ sở dữ liệu PostgreSQL:
docker start mimic-postgres

# 2. Khởi chạy giao diện Chatbot:
python -m streamlit run app.py

# 3. Chạy đánh giá Ablation nhanh:
python evaluate.py --quick
```
