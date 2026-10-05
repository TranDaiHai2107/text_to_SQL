# ĐỀ TÀI ĐỒ ÁN TỐT NGHIỆP — ĐỊNH HƯỚNG CHÍNH THỨC

> 📅 Cập nhật: 06/09/2026  
> 🎓 Khoa Công nghệ Thông tin — Trường Đại học Công nghệ Thông tin (UIT)  

---

## 1. TÊN ĐỀ TÀI

### Tiếng Việt:
> **Hệ thống chuyển đổi câu hỏi tiếng Việt sang SQL hai chiều cho dữ liệu y tế lâm sàng: Kiến trúc RAG đa tầng kết hợp Agentic Self-Correction và Diễn giải kết quả trên cơ sở dữ liệu MIMIC-IV**

### Tiếng Anh:
> **Closed-Loop Cross-lingual Text-to-SQL for Clinical Data: A Multi-layer RAG Architecture with Agentic Self-Correction and Result Interpretation on MIMIC-IV**

---

## 2. BÀI TOÁN VÀ ĐỘNG LỰC NGHIÊN CỨU

### 2.1. Vấn đề thực tế trong Y tế
Tại các bệnh viện và viện nghiên cứu, dữ liệu bệnh nhân (hồ sơ nhập viện, mã chẩn đoán ICD, xét nghiệm sinh hóa, đơn thuốc, chuyển khoa...) được lưu trữ trong **cơ sở dữ liệu quan hệ (RDBMS)**. Khi bác sĩ hoặc nhà nghiên cứu lâm sàng muốn khai thác dữ liệu, họ gặp phải các rào cản nghiêm trọng:
- Hầu hết y bác sĩ không có kỹ năng lập trình SQL.
- Cấu trúc cơ sở dữ liệu y tế (như MIMIC-IV) vô cùng phức tạp: hàng chục bảng liên kết, hàng trăm trường thuộc tính.
- Thuật ngữ bệnh học đời thường (tiếng Việt: *"suy tim"*, *"viêm phổi thùy"*, *"tiểu đường type 2"*) phải được quy chuẩn sang các mã danh mục chuẩn quốc tế (ICD-9, ICD-10) tiếng Anh trong cơ sở dữ liệu.
- Các câu hỏi liên tiếp trong quá trình chẩn đoán thường có tính kế thừa ngữ cảnh cao (ví dụ: *"trong đó có bao nhiêu nam?"* sau khi đã hỏi về nhóm bệnh nhân nữ).
- Bác sĩ cần câu trả lời kết luận rõ ràng bằng ngôn ngữ tự nhiên, không chỉ đơn thuần là một bảng dữ liệu chứa mã số kỹ thuật.

### 2.2. Giải pháp Đề xuất: Hệ thống Khép kín Hai chiều (Closed-Loop Pipeline)

```
[Bác sĩ hỏi tiếng Việt]
  "Có bao nhiêu bệnh nhân bị viêm phổi tử vong trong viện?"
        │
        ▼ (Chiều xuôi: Text-to-SQL qua RAG 3 tầng + Validator + Self-Correction)
[Cơ sở dữ liệu MIMIC-IV trên PostgreSQL]
  Thực thi câu SQL chuẩn xác → Trả về bảng kết quả (DataFrame)
        │
        ▼ (Chiều ngược: SQL-to-Text / Result Interpretation)
[Câu trả lời Ngôn ngữ Tự nhiên tiếng Việt]
  "Có tổng cộng 12 bệnh nhân được chẩn đoán viêm phổi đã tử vong trong thời gian nằm viện."
```

### 2.3. Dữ liệu Sử dụng
**MIMIC-IV** (Medical Information Mart for Intensive Care, v3.1) — cơ sở dữ liệu y tế công khai chuẩn mực quốc tế do Viện Công nghệ Massachusetts (MIT) và Beth Israel Deaconess Medical Center duy trì:
- **Tập con triển khai (MIMIC-IV Mini):** Dữ liệu tiêu biểu, 31 bảng cốt lõi (22 bảng hosp + 9 bảng icu).
- **Quy mô:** Hơn 236,000 dòng dữ liệu thực tế, lưu trữ trên hệ quản trị cơ sở dữ liệu PostgreSQL.

---

## 3. TÍNH MỚI KHOA HỌC (NOVELTY CLAIMS)

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
           BiomedSQL,        ╔═════════════════════════╗
           M3 System)        ║    ĐỒ ÁN NÀY            ║ ← BẠN ĐANG Ở ĐÂY
                             ║ (5 Điểm mới khoa học)   ║
                             ╚═════════════════════════╝
```

### Năm hướng đóng góp cần được kiểm chứng bằng tổng quan tài liệu và thực nghiệm:

| # | Điểm mới khoa học | Chi tiết & Đóng góp | So sánh với các công trình gần nhất |
|---|---|---|---|
| **1** | **Text-to-SQL y tế tiếng Việt** | Khảo sát khả năng hỏi MIMIC-IV bằng tiếng Việt và đo trên benchmark nội bộ 180 câu. Không tuyên bố “đầu tiên” khi chưa có systematic review. | So sánh có kiểm soát với EHRSQL và các hệ thống MIMIC-IV gần đây |
| **2** | **Kiến trúc RAG 3 tầng cho dữ liệu lâm sàng** | Phân rã thành ICD Dictionary, Schema Selection và Few-shot SQL Examples; đánh giá đóng góp từng tầng bằng ablation. | Kết luận dựa trên VSR/EX theo cùng dataset và protocol |
| **3** | **Màng lọc Schema-Aware SQL Validator + Vòng lặp Agentic Self-Correction** | Dùng SQLGlot AST để kiểm tra statement, alias, CTE, bảng/cột và điều kiện JOIN trước khi chạy; runtime tiếp tục dùng role/transaction chỉ đọc, timeout và row cap. Nếu có lỗi, tác tử phản hồi và tái sinh SQL (tối đa 2 lần). | Cần đánh giá thực nghiệm so với các baseline validator/correction |
| **4** | **Xử lý hội thoại đa lượt** | Viết lại câu hỏi tỉnh lược tiếng Việt dựa trên lịch sử, SQL và tóm tắt kết quả; cần đánh giá riêng trên `test_multiturn.json` và mở rộng bộ test. | So sánh với baseline không rewrite và rewrite chỉ dùng văn bản |
| **5** | **Luồng Text-to-SQL và trình bày kết quả** | Kết hợp sinh SQL, thực thi có giới hạn, bảng/biểu đồ và diễn giải cục bộ hoặc qua LLM khi được bật rõ ràng. | Đánh giá tính hữu dụng người dùng tách khỏi Execution Accuracy |

---

## 4. KIẾN TRÚC TỔNG THỂ HỆ THỐNG

```
 NGƯỜI DÙNG (Bác sĩ / Nhà nghiên cứu)
 ┌─────────────────────────────────────────────────────────────┐
 │  Câu hỏi tiếng Việt: "Trong số đó, có bao nhiêu người nam?"  │
 └──────────────────────────────┬──────────────────────────────┘
                                │
 ═══════════════════════════════╪══════════════════════════════════════════════════
  MODULE 1: CONTEXT-AWARE MULTI-TURN QUERY REWRITING
 ═══════════════════════════════╪══════════════════════════════════════════════════
                                ▼
  Kế thừa: Câu hỏi trước + SQL trước + Kết quả trước
  → Viết lại thành câu độc lập: "Trong số bệnh nhân nữ, có bao nhiêu bệnh nhân nam?"
                                │
 ═══════════════════════════════╪══════════════════════════════════════════════════
  MODULE 2: RETRIEVAL-AUGMENTED GENERATION (RAG 3 TẦNG)
 ═══════════════════════════════╪══════════════════════════════════════════════════
                                ▼
  ┌─────────────────────────────────────────────────────────────────────────────┐
  │ Tầng 1: ICD Dictionary Retrieval (ChromaDB - 10,000 mã)                     │
  │ → Ánh xạ triệu chứng, tên bệnh tiếng Việt sang ICD-9 / ICD-10 quốc tế       │
  │                                                                             │
  │ Tầng 2: Schema Selection Retrieval (ChromaDB - 31 bảng)                     │
  │ → Lọc lấy 3-5 bảng liên quan + DDL cột chuẩn xác (giảm tải context)         │
  │                                                                             │
  │ Tầng 3: Few-shot SQL Examples Retrieval (ChromaDB - 101 cặp Gold Q-SQL)       │
  │ → Trích xuất 3 cặp câu hỏi - SQL mẫu có cấu trúc ngữ nghĩa tương đồng nhất │
  └──────────────────────────────┬──────────────────────────────────────────────┘
                                 │
 ════════════════════════════════╪═════════════════════════════════════════════════
  MODULE 3: PROMPT COMPOSER & LLM GENERATION
 ════════════════════════════════╪═════════════════════════════════════════════════
                                 ▼
  Ghép: System Prompt (gồm Subquery Rule) + ICD + Schema DDL + Examples + Câu hỏi
  → Gửi qua Groq API (Qwen 2.5 27B / Llama 3.3 70B, max_tokens=900 chống 429)
  → Sinh câu lệnh SQL ứng viên
                                 │
 ════════════════════════════════╪═════════════════════════════════════════════════
  MODULE 4: SCHEMA-AWARE SQL VALIDATOR
 ════════════════════════════════╪═════════════════════════════════════════════════
                                 ▼
  Kiểm tra AST bằng SQLGlot trước khi chạm vào cơ sở dữ liệu:
  ✓ Bảng có tồn tại? Cột có thuộc bảng?
  ✓ JOIN có đủ cả icd_code VÀ icd_version?
  → Nếu vi phạm → Tạo phản hồi chi tiết yêu cầu LLM tự sửa
                                 │
 ════════════════════════════════╪═════════════════════════════════════════════════
  MODULE 5: AGENTIC SELF-CORRECTION LOOP & DB EXECUTION
 ════════════════════════════════╪═════════════════════════════════════════════════
                                 ▼
  Thực thi truy vấn trên PostgreSQL (MIMIC-IV):
  → Nếu thành công: Trả về DataFrame kết quả
  → Nếu runtime error: Phản hồi traceback cho LLM tự sửa (tối đa 2 lần retry)
                                 │
 ════════════════════════════════╪═════════════════════════════════════════════════
  MODULE 6: BIDIRECTIONAL RESULT INTERPRETATION (SQL-to-Text)
 ════════════════════════════════╪═════════════════════════════════════════════════
                                 ▼
  Chuyển đổi bảng dữ liệu định lượng thành câu trả lời tự nhiên tiếng Việt:
  💬 "Trong nhóm bệnh nhân nữ được khảo sát, không có bệnh nhân nam nào (0 ca)."
  + Bảng dữ liệu chi tiết + Biểu đồ trực quan hóa + Nút tải file CSV
```

---

## 5. BẢNG THEO DÕI TIẾN ĐỘ CÔNG VIỆC

| STT | Nhiệm vụ / Hạng mục | Trạng thái | Minh chứng / File mã nguồn |
|:---:|---|:---:|---|
| 1 | Nhúng đa ngôn ngữ tiếng Việt (Multilingual Embedding) | ✅ Hoàn thành | `embedding_config.py` (`paraphrase-multilingual-MiniLM-L12-v2`) |
| 2 | RAG Tầng 1: ICD-9 & ICD-10 Dictionary Collection | ✅ Hoàn thành | `rag_engine.py` (`retrieve_icd_codes`) |
| 3 | RAG Tầng 2: Schema Selection Collection | ✅ Hoàn thành | `rag_engine.py` (`retrieve_schema`), `mimic_schema.json` |
| 4 | RAG Tầng 3: Few-shot SQL Examples Collection | ✅ Hoàn thành | `rag_engine.py` (`retrieve_examples`), `mimic_examples.json` |
| 5 | Schema-Aware SQL Validator (SQLGlot AST + schema qualification) | ✅ Hoàn thành | `sql_validator.py` (`validate_sql_schema`) |
| 6 | Agentic Self-Correction Loop (Vòng lặp tự sửa lỗi) | ✅ Hoàn thành | `rag_engine.py` (`generate_sql_with_correction`) |
| 7 | Context-Aware Multi-turn Query Rewriter (Kèm Subquery Logic) | ✅ Hoàn thành | `rag_engine.py` (`rewrite_question`), quy tắc Rule 8 |
| 8 | Diễn giải kết quả hai chiều (SQL-to-Text Clinical Interpretation) | ✅ Hoàn thành | `rag_engine.py` (`interpret_result`) |
| 9 | Tối ưu hóa hạn mức gọi LLM (Chống 429 Groq Rate Limit) | ✅ Hoàn thành | Cấu hình `max_tokens=900/256` trong `rag_engine.py` |
| 10 | Chuẩn hóa bộ dữ liệu kiểm thử (180 Test Cases có Gold SQL) | ✅ Hoàn thành | `test_dataset.json` (4 cấp độ Easy, Medium, Hard, Complex) |
| 11 | Giao diện Chatbot tương tác thông minh (Streamlit UI) | ✅ Hoàn thành | `app.py` (Visual RAG tags, khung tím gradient, Dashboard Ablation) |
| 12 | Script đo lường thực nghiệm khoa học tự động (Ablation Study) | ✅ Hoàn thành | `evaluate.py` (Hỗ trợ cờ `--quick` và `--modes`) |
| 13 | Cơ sở dữ liệu PostgreSQL (MIMIC-IV trên Docker) | ✅ Hoàn thành | Container `mimic-postgres` đang hoạt động và kết nối tốt |
| 14 | Chạy thực nghiệm thu thập số liệu chính thức (Ablation Study) | ⏳ Sẵn sàng | Có thể chạy `python evaluate.py --quick` ngay |
| 15 | Hoàn thiện bản thảo thuyết minh Luận văn Tốt nghiệp | ⏳ Đang tiến hành | Đã có sẵn đề cương chi tiết 6 chương |

---

## 6. THIẾT KẾ ĐÁNH GIÁ THỰC NGHIỆM (ABLATION STUDY)

Hệ thống đánh giá trên 180 câu hỏi độc lập dựa trên 2 chỉ số tiêu chuẩn quốc tế:
1. **Valid SQL Rate (VSR):** Tỷ lệ câu lệnh SQL hợp lệ về mặt cú pháp và runtime trên PostgreSQL.
2. **Execution Accuracy (EX):** Tỷ lệ câu SQL cho ra bảng dữ liệu trùng khớp tuyệt đối (sử dụng phương pháp so sánh tập hợp hàng frozenset không phụ thuộc thứ tự) với Gold SQL của chuyên gia.

### Thiết kế 6 chế độ Ablation:
- `base`: Baseline LLM thuần túy, không có RAG, sử dụng schema tĩnh cứng.
- `icd`: Chỉ kích hoạt tầng RAG tra cứu mã bệnh ICD.
- `schema`: Chỉ kích hoạt tầng RAG chọn lọc lược đồ bảng (Schema Selection).
- `examples`: Chỉ kích hoạt tầng RAG gợi ý câu hỏi mẫu (Few-shot Examples).
- `full`: Toàn bộ kiến trúc đề xuất (3 tầng RAG).
- `full_agentic`: Full RAG + Vòng lặp tự sửa lỗi Agentic (Schema Validator + Runtime Feedback).
