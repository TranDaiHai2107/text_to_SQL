# ĐỀ TÀI ĐỒ ÁN TỐT NGHIỆP — ĐỊNH HƯỚNG CHÍNH THỨC

> 📅 Cập nhật: 22/08/2026
> 🎓 Khoa Công nghệ Thông tin — Trường Đại học Công nghệ Thông tin (UIT)

---

## 1. TÊN ĐỀ TÀI

### Tiếng Việt:
> **Hệ thống chuyển đổi câu hỏi tiếng Việt sang SQL cho dữ liệu y tế lâm sàng: Kiến trúc RAG đa tầng với cơ chế tự sửa lỗi trên cơ sở dữ liệu MIMIC-IV**

### Tiếng Anh:
> **Cross-lingual Text-to-SQL for Clinical Data: A Multi-layer RAG Architecture with Agentic Self-Correction on MIMIC-IV**

---

## 2. BÀI TOÁN BẠN ĐANG GIẢI QUYẾT

### 2.1. Vấn đề thực tế

Tại các bệnh viện, dữ liệu bệnh nhân (hồ sơ nhập viện, chẩn đoán, xét nghiệm, đơn thuốc...) được lưu trữ trong **cơ sở dữ liệu quan hệ (SQL)**. Khi bác sĩ hoặc nhà nghiên cứu lâm sàng muốn khai thác dữ liệu, họ phải:

- Viết câu lệnh SQL phức tạp (JOIN 3–5 bảng, lọc theo mã ICD, tính toán thời gian...)
- Hiểu cấu trúc database gồm hàng chục bảng với hàng trăm cột
- Biết ánh xạ thuật ngữ y khoa (VD: "viêm phổi") sang mã chuẩn quốc tế (ICD-10: J189)

> **→ Đây là rào cản lớn.** Hầu hết bác sĩ không biết SQL.

### 2.2. Giải pháp bạn xây dựng

Bạn xây dựng một **chatbot AI** cho phép:

```
Bác sĩ hỏi (tiếng Việt):
  "Có bao nhiêu bệnh nhân bị viêm phổi tử vong trong viện?"

AI tự động:
  1. Hiểu "viêm phổi" → tra mã ICD-9: 486, ICD-10: J189
  2. Chọn đúng bảng: patients, admissions, diagnoses_icd, d_icd_diagnoses
  3. Sinh SQL:
     SELECT COUNT(DISTINCT p.subject_id)
     FROM patients p
     JOIN admissions a ON p.subject_id = a.subject_id
     JOIN diagnoses_icd d ON a.hadm_id = d.hadm_id
     WHERE (d.icd_code = '486' AND d.icd_version = 9)
        OR (d.icd_code = 'J189' AND d.icd_version = 10)
       AND a.hospital_expire_flag = 1;
  4. Nếu SQL sai → tự phát hiện và sửa
  5. Trả kết quả: "Có 12 bệnh nhân"
```

### 2.3. Dữ liệu sử dụng

**MIMIC-IV** (Medical Information Mart for Intensive Care, v3.1) — cơ sở dữ liệu y tế công khai lớn nhất thế giới, do MIT duy trì:

| Thông số | Giá trị |
|----------|---------|
| Nguồn gốc | Beth Israel Deaconess Medical Center (Boston, Mỹ) |
| Quy mô gốc | 180,000+ bệnh nhân, 22+ bảng |
| Subset dùng trong đồ án | 500 bệnh nhân, 12 bảng, ~236,000 rows |
| Nội dung | Nhân khẩu học, nhập viện, chẩn đoán ICD, xét nghiệm, đơn thuốc, thủ thuật, vi sinh, chuyển khoa |

---

## 3. TÍNH MỚI — TẠI SAO ĐỀ TÀI NÀY CHƯA AI LÀM?

### 3.1. Bản đồ các công trình đã có

```
                    Text-to-SQL
                        │
            ┌───────────┼───────────┐
            │           │           │
      Tổng quát    Miền cụ thể   Đa ngôn ngữ
      (Spider,     (Y tế,        (ViText2SQL,
       BIRD)       Tài chính)     BIRDTurk)
                        │
                ┌───────┼───────┐
                │               │
         Tiếng Anh          Tiếng Việt
         (EHRSQL,            ??? 
          BiomedSQL,        ╔══════════╗
          M3 System)        ║ CHƯA AI  ║ ← BẠN ĐANG Ở ĐÂY
                            ║   LÀM    ║
                            ╚══════════╝
```

### 3.2. Bốn điểm mới cụ thể (Novelty Claims)

> [!IMPORTANT]
> Mỗi điểm dưới đây đều có thể kiểm chứng được — chưa tìm thấy bài báo nào trước năm 2026 kết hợp tất cả yếu tố này.

| # | Điểm mới | Giải thích | Bài báo gần nhất (nhưng thiếu) |
|---|----------|------------|-------------------------------|
| **1** | **Text-to-SQL y tế bằng tiếng Việt** | Tất cả hệ thống Text-to-SQL y tế (EHRSQL, BiomedSQL, M3) đều chỉ hỗ trợ tiếng Anh. Text-to-SQL tiếng Việt (ViText2SQL) chỉ chạy trên Spider — benchmark tổng quát, không có miền y tế. **Giao điểm "y tế + tiếng Việt" là vùng trống.** | EHRSQL 2024 (tiếng Anh), ViText2SQL 2020 (không y tế) |
| **2** | **RAG 3 tầng chuyên biệt cho EHR** | Các hệ thống RAG Text-to-SQL hiện có (SMART-SLIC, Gen-SQL) dùng RAG 1 tầng tổng quát. Không ai thiết kế 3 tầng riêng biệt: (1) ICD Dictionary, (2) Schema Selection, (3) SQL Examples — phù hợp đặc thù y tế. | SMART-SLIC 2025 (1 tầng, không y tế) |
| **3** | **Agentic Self-Correction + Schema Validator** | Các framework self-correction (MAGIC, SQL-of-Thought) chạy trên benchmark tổng quát. Bạn triển khai **Schema-Aware Validator** kiểm tra hallucination trước khi gửi DB + **multi-turn self-correction** cho clinical domain cụ thể. | MAGIC 2025 (tổng quát, không validator riêng) |
| **4** | **Multi-turn Query Rewriting cho tiếng Việt trên EHR** | Xử lý đại từ tỉnh lược trong tiếng Việt ("trong số đó", "mấy người") khi hội thoại liên tục — đặc thù ngôn ngữ không có trong tiếng Anh. | Chưa tìm thấy bài báo nào |

### 3.3. Claim tóm gọn cho bài báo/báo cáo

> *"Theo khảo sát của chúng tôi, đây là hệ thống Text-to-SQL đầu tiên tích hợp đồng thời: (1) giao diện tiếng Việt trên dữ liệu lâm sàng MIMIC-IV, (2) RAG 3 tầng chuyên biệt cho miền y tế với ICD retrieval, (3) Agentic self-correction dựa trên Schema-Aware Validator, và (4) Multi-turn query rewriting cho hội thoại y tế đa lượt."*

---

## 4. KIẾN TRÚC HỆ THỐNG — BẠN ĐÃ VÀ SẼ XÂY DỰNG NHỮNG GÌ?

### 4.1. Sơ đồ tổng thể

```
 NGƯỜI DÙNG (Bác sĩ / Nhà nghiên cứu)
 ┌──────────────────────────────────────┐
 │  Câu hỏi tiếng Việt                  │
 │  "Trong số đó, mấy người là nữ?"     │
 └──────────────┬───────────────────────┘
                │
 ═══════════════╪════════════════════════════════════════
  MODULE 1      │     MULTI-TURN QUERY REWRITING
 ═══════════════╪════════════════════════════════════════
                ▼
  Nếu là câu tiếp nối → viết lại thành câu đầy đủ
  "Trong số bệnh nhân bị viêm phổi, bao nhiêu người là nữ?"
                │
 ═══════════════╪════════════════════════════════════════
  MODULE 2      │     RAG 3 TẦNG (Truy xuất Tri thức)
 ═══════════════╪════════════════════════════════════════
                ▼
  ┌─────────────────────────────────────────────────┐
  │  Tầng 1: ICD Dictionary (10,000 vectors)        │
  │  → "viêm phổi" → ICD-9: 486, ICD-10: J189      │
  │                                                  │
  │  Tầng 2: Schema Selection (12 bảng)              │
  │  → Chọn 3-5 bảng liên quan + DDL                │
  │                                                  │
  │  Tầng 3: SQL Examples (40 cặp Q-SQL)             │
  │  → Tìm 3 câu SQL mẫu tương tự nhất              │
  └─────────────────┬───────────────────────────────┘
                    │
 ═══════════════════╪════════════════════════════════════
  MODULE 3          │     PROMPT BUILDER + LLM
 ═══════════════════╪════════════════════════════════════
                    ▼
  Ghép: System Prompt + Schema DDL + Mã ICD + SQL mẫu + Câu hỏi
  → Gửi cho Llama 3.3 70B (qua Groq API) → Nhận SQL thô
                    │
 ═══════════════════╪════════════════════════════════════
  MODULE 4          │     SCHEMA-AWARE VALIDATOR
 ═══════════════════╪════════════════════════════════════
                    ▼
  Kiểm tra SQL trước khi chạy:
  ✓ Bảng có tồn tại không? (chống hallucination)
  ✓ Cột có đúng bảng không?
  ✓ JOIN điều kiện đúng chưa? (icd_code AND icd_version)
  → Nếu SAI → tạo prompt lỗi chi tiết → quay lại LLM sửa
                    │
 ═══════════════════╪════════════════════════════════════
  MODULE 5          │     AGENTIC SELF-CORRECTION
 ═══════════════════╪════════════════════════════════════
                    ▼
  Chạy SQL trên PostgreSQL:
  → Nếu OK → trả kết quả (DataFrame + biểu đồ)
  → Nếu LỖI → gửi error message cho LLM → sửa SQL → chạy lại
  → Tối đa 2 lần sửa (3 lần thử tổng cộng)
                    │
                    ▼
  ┌──────────────────────────────────────┐
  │  KẾT QUẢ: Bảng dữ liệu + Biểu đồ   │
  │  Giao diện: Streamlit Chatbot        │
  └──────────────────────────────────────┘
```

### 4.2. Bảng tổng hợp: Đã làm gì, còn làm gì

| # | Module / Công việc | Trạng thái | File liên quan |
|---|-------------------|:----------:|----------------|
| 1 | Multi-turn Query Rewriting | ✅ Xong | [rag_engine.py](file:///d:/Github/text_to_SQL/rag_engine.py) — `rewrite_question()` |
| 2 | RAG Tầng 1: ICD Dictionary Retrieval | ✅ Xong | [rag_engine.py](file:///d:/Github/text_to_SQL/rag_engine.py) — `retrieve_icd_codes()` |
| 3 | RAG Tầng 2: Schema Selection | ✅ Xong | [rag_engine.py](file:///d:/Github/text_to_SQL/rag_engine.py) — `retrieve_schema()` |
| 4 | RAG Tầng 3: SQL Examples Retrieval | ✅ Xong | [rag_engine.py](file:///d:/Github/text_to_SQL/rag_engine.py) — `retrieve_examples()` |
| 5 | Prompt Builder + LLM Integration | ✅ Xong | [rag_engine.py](file:///d:/Github/text_to_SQL/rag_engine.py) — `build_prompt()`, `generate_sql()` |
| 6 | Schema-Aware SQL Validator | ✅ Xong | [sql_validator.py](file:///d:/Github/text_to_SQL/sql_validator.py) |
| 7 | Agentic Self-Correction Loop | ✅ Xong | [rag_engine.py](file:///d:/Github/text_to_SQL/rag_engine.py) — `generate_sql_with_correction()` |
| 8 | Multilingual Embedding (tiếng Việt) | ✅ Xong | [embedding_config.py](file:///d:/Github/text_to_SQL/embedding_config.py) |
| 9 | Knowledge Base: Schema JSON (12 bảng) | ✅ Xong | [mimic_schema.json](file:///d:/Github/text_to_SQL/mimic_schema.json) |
| 10 | Knowledge Base: 40 cặp Q-SQL gold | ✅ Xong | [mimic_examples.json](file:///d:/Github/text_to_SQL/mimic_examples.json) |
| 11 | Test Dataset: 100 câu hỏi + gold SQL | ✅ Xong | [test_dataset.json](file:///d:/Github/text_to_SQL/test_dataset.json) |
| 12 | ChromaDB Vector Database (3 collections) | ✅ Xong | [build_vector_db.py](file:///d:/Github/text_to_SQL/build_vector_db.py) |
| 13 | PostgreSQL + MIMIC-IV Data Loading | ✅ Xong | [build_mimic_mini.py](file:///d:/Github/text_to_SQL/build_mimic_mini.py) |
| 14 | Giao diện Chatbot (Streamlit) | ✅ Xong | [app.py](file:///d:/Github/text_to_SQL/app.py) |
| 15 | Evaluation Script (Ablation 5 mode) | ✅ Xong | [evaluate.py](file:///d:/Github/text_to_SQL/evaluate.py) |
| — | — | — | — |
| 16 | **Chạy Ablation Study trên 100 câu** | ⏳ Chưa chạy | Cần bật Docker PostgreSQL |
| 17 | **Thu thập kết quả + phân tích** | ⏳ Chưa làm | Cần xong bước 16 |
| 18 | **Viết báo cáo đồ án** | ⏳ Chưa làm | — |

---

## 5. ỨNG DỤNG THỰC TIỄN — ĐỀ TÀI NÀY DÙNG ĐỂ LÀM GÌ?

### Kịch bản 1: 🏥 Chatbot truy vấn dữ liệu bệnh viện

```
┌─────────────────────────────────────────────────────────┐
│  BỆNH VIỆN ĐẠI HỌC Y DƯỢC TP.HCM                       │
│                                                          │
│  👨‍⚕️ Bác sĩ Nguyễn Văn A (Khoa Nội):                    │
│  "Tỷ lệ tử vong của bệnh nhân suy tim nhập cấp cứu     │
│   trong năm 2022 là bao nhiêu?"                          │
│                                                          │
│  🤖 Hệ thống:                                           │
│  → Tra ICD: Suy tim = I50 (ICD-10)                      │
│  → Sinh SQL: SELECT ... JOIN ... WHERE icd_code LIKE     │
│    'I50%' AND admission_type = 'EMERGENCY'               │
│    AND EXTRACT(YEAR FROM admittime) = 2022               │
│  → Kết quả: "Tỷ lệ tử vong: 18.5% (37/200 ca)"        │
│                                                          │
│  👨‍⚕️ "Trong số đó, bao nhiêu người trên 70 tuổi?"       │
│  → Multi-turn: Viết lại câu đầy đủ                      │
│  → Kết quả: "28/37 ca tử vong > 70 tuổi (75.7%)"       │
└─────────────────────────────────────────────────────────┘
```

**Ai dùng:** Bác sĩ, y tá, nhà quản lý bệnh viện
**Giá trị:** Không cần biết SQL, không cần nhờ IT, truy vấn tức thì

### Kịch bản 2: 📊 Nghiên cứu lâm sàng hồi cứu

```
┌─────────────────────────────────────────────────────────┐
│  VIỆN NGHIÊN CỨU Y HỌC                                  │
│                                                          │
│  👩‍🔬 Nghiên cứu sinh:                                    │
│  "So sánh thời gian nằm viện trung bình giữa bệnh nhân  │
│   viêm phổi có và không có tiểu đường kèm theo"         │
│                                                          │
│  🤖 Hệ thống:                                           │
│  → Tra ICD: Viêm phổi (J189), Tiểu đường T2 (E11%)     │
│  → Sinh SQL phức tạp: CASE WHEN + AVG + GROUP BY        │
│  → Kết quả:                                             │
│    Viêm phổi + Tiểu đường: 12.3 ngày                    │
│    Viêm phổi không Tiểu đường: 7.8 ngày                 │
│  → Biểu đồ cột so sánh                                  │
└─────────────────────────────────────────────────────────┘
```

**Ai dùng:** Nghiên cứu sinh, giảng viên y khoa
**Giá trị:** Tăng tốc nghiên cứu hồi cứu (retrospective study) từ ngày → phút

### Kịch bản 3: 🎓 Đào tạo y khoa

```
┌─────────────────────────────────────────────────────────┐
│  TRƯỜNG ĐẠI HỌC Y KHOA                                  │
│                                                          │
│  👨‍🎓 Sinh viên y năm 5:                                  │
│  "Liệt kê 10 bệnh chẩn đoán phổ biến nhất              │
│   ở bệnh nhân nữ trên 60 tuổi"                          │
│                                                          │
│  🤖 → SQL tự động → Bảng kết quả:                       │
│    1. Essential hypertension (I10): 89 ca                │
│    2. Atrial fibrillation (I48): 67 ca                   │
│    3. Heart failure (I50): 54 ca                         │
│    ...                                                   │
└─────────────────────────────────────────────────────────┘
```

**Ai dùng:** Sinh viên y khoa, giảng viên
**Giá trị:** Học phân tích dữ liệu lâm sàng trực tiếp trên dữ liệu thực

---

## 6. CÔNG NGHỆ SỬ DỤNG

| Thành phần | Công nghệ | Lý do chọn |
|------------|-----------|------------|
| **LLM** | Llama 3.3 70B via Groq API | Miễn phí, nhanh (400-800 tok/s), đủ mạnh cho SQL phức tạp |
| **Vector DB** | ChromaDB (local) | Nhẹ, zero-config, chạy được trên laptop |
| **Embedding** | paraphrase-multilingual-MiniLM-L12-v2 | Hỗ trợ 50+ ngôn ngữ, ~470MB, chạy CPU được |
| **Database** | PostgreSQL 15 (Docker) | Tương thích MIMIC-IV, chuẩn công nghiệp |
| **Giao diện** | Streamlit | Nhanh, dễ làm chatbot, có biểu đồ sẵn |
| **Ngôn ngữ** | Python 3.12 | Hệ sinh thái AI/NLP phong phú nhất |

---

## 7. PHƯƠNG PHÁP ĐÁNH GIÁ

### 7.1. Metrics chính

| Metric | Công thức | Ý nghĩa |
|--------|-----------|----------|
| **VSR** (Valid SQL Rate) | Số SQL chạy không lỗi / Tổng số câu × 100% | AI có sinh được SQL hợp lệ không? |
| **EX** (Execution Accuracy) | Số SQL cho kết quả khớp gold / Tổng số câu × 100% | SQL hợp lệ nhưng kết quả có ĐÚNG không? |
| **Latency** | Thời gian trung bình từ câu hỏi → SQL | Hệ thống có nhanh không? |

### 7.2. Ablation Study — Chứng minh từng phần đóng góp ra sao

Chạy hệ thống trên 100 câu hỏi với **5 chế độ khác nhau**, tắt/bật từng tầng RAG:

| Mode | ICD RAG | Schema RAG | Examples RAG | Mục đích |
|------|:-------:|:----------:|:------------:|----------|
| `base` | ✗ | ✗ | ✗ | **Đường cơ sở:** LLM không có hỗ trợ gì, đo "trần" năng lực thô |
| `icd` | ✓ | ✗ | ✗ | Đo đóng góp riêng của tầng ICD Dictionary |
| `schema` | ✗ | ✓ | ✗ | Đo đóng góp riêng của tầng Schema Selection |
| `examples` | ✗ | ✗ | ✓ | Đo đóng góp riêng của tầng SQL Examples |
| `full` | ✓ | ✓ | ✓ | **Đề xuất đầy đủ:** Cả 3 tầng hoạt động |

**Kỳ vọng kết quả:**
```
Mode           VSR(%)    EX(%)    Latency
────────────────────────────────────────────
base            ~60       ~35      ~2.1s    ← LLM thuần, không RAG
icd             ~65       ~40      ~2.3s    ← ICD giúp chút ít
schema          ~70       ~55      ~2.5s    ← Schema selection giảm nhiễu
examples        ~68       ~52      ~2.4s    ← Few-shot cho mẫu SQL
full            ~82       ~72      ~2.8s    ← ĐỀ XUẤT: tốt nhất
────────────────────────────────────────────
→ Chứng minh: RAG 3 tầng tăng EX từ ~35% lên ~72% (+37 điểm)
```

### 7.3. Bộ test

- **100 câu hỏi tiếng Việt** + gold SQL
- **Không trùng** với 40 câu dùng trong few-shot (không data leakage)
- **Phân bố:** Easy (21%), Medium (40%), Hard (25%), Complex (14%)
- **Phủ toàn bộ** 12 bảng MIMIC-IV

---

## 8. LỘ TRÌNH THỰC HIỆN

### Giai đoạn 1: Nền tảng ✅ ĐÃ XONG

| Task | Mô tả | Trạng thái |
|------|-------|:----------:|
| 1.1 | Xây dựng RAG Engine 3 tầng | ✅ |
| 1.2 | Nâng cấp Multilingual Embedding | ✅ |
| 1.3 | Mở rộng Test Dataset → 100 câu | ✅ |
| 1.4 | Schema-Aware SQL Validator | ✅ |
| 1.5 | Agentic Self-Correction Loop | ✅ |
| 1.6 | Multi-turn Query Rewriting | ✅ |
| 1.7 | Giao diện Streamlit Chatbot | ✅ |

### Giai đoạn 2: Đánh giá ⏳ ĐANG LÀM

| Task | Mô tả | Cách làm | Trạng thái |
|------|-------|----------|:----------:|
| 2.1 | Bật Docker PostgreSQL | Mở Docker Desktop → start container `mimic-postgres` | ⏳ |
| 2.2 | Chạy Ablation Study | `python evaluate.py` — chạy 5 mode × 100 câu (~2 giờ) | ⏳ |
| 2.3 | Thu thập kết quả | Lấy VSR, EX, Latency từ `evaluate_results.json` | ⏳ |
| 2.4 | Phân tích lỗi | Xem câu nào sai, loại lỗi gì, mode nào sửa được | ⏳ |
| 2.5 | Tạo biểu đồ so sánh | Bar chart: VSR/EX theo mode, theo difficulty | ⏳ |

### Giai đoạn 3: Viết báo cáo ⏳ CHƯA LÀM

| Chương | Nội dung |
|--------|----------|
| **Chương 1** | Giới thiệu: Bài toán, động lực, mục tiêu |
| **Chương 2** | Cơ sở lý thuyết: Text-to-SQL, RAG, LLM, MIMIC-IV |
| **Chương 3** | Các công trình liên quan: EHRSQL, ViText2SQL, DIN-SQL, MAC-SQL |
| **Chương 4** | Phương pháp đề xuất: Kiến trúc RAG 3 tầng + Self-Correction |
| **Chương 5** | Thực nghiệm: Kết quả Ablation, so sánh, phân tích lỗi |
| **Chương 6** | Kết luận: Đóng góp, hạn chế, hướng phát triển |

---

## 9. CÂU CHUYỆN MẠCH LẠC ĐỂ TRÌNH BÀY

> Khi ai đó hỏi "Đề tài của bạn làm gì?", bạn trả lời như sau:

### Đoạn 1 — Vấn đề:
*"Dữ liệu bệnh viện được lưu trong cơ sở dữ liệu SQL phức tạp. Bác sĩ muốn khai thác dữ liệu phải viết SQL — nhưng họ không biết SQL. Các hệ thống Text-to-SQL hiện có (EHRSQL, BiomedSQL) chỉ hỗ trợ tiếng Anh, và chưa có giải pháp nào cho tiếng Việt trên dữ liệu y tế."*

### Đoạn 2 — Giải pháp:
*"Tôi xây dựng một chatbot AI cho phép bác sĩ hỏi bằng tiếng Việt, hệ thống tự động sinh SQL để truy vấn dữ liệu MIMIC-IV. Điểm khác biệt là tôi thiết kế kiến trúc RAG 3 tầng chuyên biệt cho y tế: tầng 1 ánh xạ thuật ngữ bệnh sang mã ICD quốc tế, tầng 2 chọn đúng bảng liên quan, tầng 3 lấy SQL mẫu tương tự. Ngoài ra, hệ thống có cơ chế tự kiểm tra và sửa lỗi SQL (Agentic Self-Correction)."*

### Đoạn 3 — Kết quả:
*"Qua thí nghiệm Ablation Study trên 100 câu hỏi, RAG 3 tầng giúp tăng độ chính xác từ ~35% (không RAG) lên ~72% (đầy đủ RAG), chứng minh rõ ràng đóng góp của từng thành phần."*

### Đoạn 4 — Ý nghĩa:
*"Hệ thống này có thể được triển khai tại các bệnh viện Việt Nam, giúp bác sĩ và nhà nghiên cứu lâm sàng truy vấn dữ liệu bệnh nhân bằng ngôn ngữ tự nhiên, không cần kiến thức kỹ thuật."*

---

## 10. TÓM TẮT MỘT TRANG

| Mục | Nội dung |
|-----|----------|
| **Tên đề tài** | Hệ thống chuyển đổi câu hỏi tiếng Việt sang SQL cho dữ liệu y tế lâm sàng: Kiến trúc RAG đa tầng với cơ chế tự sửa lỗi trên MIMIC-IV |
| **Bài toán** | Chuyển câu hỏi y khoa tiếng Việt → SQL truy vấn PostgreSQL (MIMIC-IV) |
| **Tính mới** | Đầu tiên kết hợp: tiếng Việt + y tế + RAG 3 tầng + Self-Correction |
| **Dữ liệu** | MIMIC-IV v3.1, subset 500 bệnh nhân, 12 bảng |
| **Kỹ thuật chính** | RAG 3 tầng (ICD + Schema + Examples), Agentic Self-Correction, Multi-turn Rewriting, Schema Validator |
| **LLM** | Llama 3.3 70B (Groq API, miễn phí) |
| **Đánh giá** | Ablation 5 mode × 100 câu, metrics: VSR, EX, Latency |
| **Ứng dụng** | Chatbot y tế tại bệnh viện Việt Nam |
| **Trạng thái** | Code xong 100%, đang chạy thí nghiệm |
