# Nghiên cứu ba công trình Text-to-SQL

Ngày rà soát: 11/11/2026. Tài liệu này chỉ ghi nhận nghiên cứu; không thêm benchmark hay mã nguồn của tác giả vào runtime MIMIC-IV hiện tại.

## 1. CLINSQL — EACL 2026

**Bài báo:** [Patient-Similarity Cohort Reasoning in Clinical Text-to-SQL](https://aclanthology.org/2026.eacl-long.64/) ([PDF](https://aclanthology.org/2026.eacl-long.64.pdf)). **Nguồn chính thức:** [GitHub Barryshen1/ClinSQL](https://github.com/Barryshen1/ClinSQL), [dataset Hugging Face yifeis02/ClinSQL](https://huggingface.co/datasets/yifeis02/ClinSQL).

CLINSQL là **benchmark**, không phải một phương pháp agent sinh SQL mới. Nó gồm 633 câu hỏi lâm sàng được chuyên gia gán nhãn trên MIMIC-IV v3.1: 190 Easy, 254 Medium, 189 Hard; sáu nhóm tình huống về bệnh nhân/nhập viện, dấu hiệu sinh tồn, xét nghiệm, thuốc, thủ thuật và chẩn đoán/kết cục. Trọng tâm là chọn cohort bệnh nhân tương tự, ghép nhiều bảng, mã lâm sàng, thời gian và phép tổng hợp. Dataset công bố câu hỏi, gold SQL BigQuery, kết quả tham chiếu và hai cây rubric cho SQL/kết quả. Trang dataset hiện hiển thị split validation 190 dòng; cần theo đúng split/protocol của repo khi đánh giá toàn bộ.

Gold SQL chạy trên BigQuery `physionet-data.mimiciv_3_1_hosp` và `..._icu`. Tái hiện yêu cầu quyền MIMIC-IV v3.1 trên PhysioNet, dự án Google Cloud/BigQuery và cấu hình xác thực. Repo cung cấp `model_inference/`, script chạy model và `evaluation/clinical_rubric_scorer.py`; lệnh mẫu là `python evaluation/clinical_rubric_scorer.py full <model_name>`. Chấm điểm bằng LLM judge trên rubric, ưu tiên điều kiện critical, có nhánh sequential và trọng số; đồng thời xem xét kết quả thực thi và tính hợp lý lâm sàng. **Execution Score của bài không nên hiểu là exact-match SQL hoặc execution accuracy nhị phân kiểu BIRD.** Bài báo ghi GPT-5-mini đạt 74,67% Execution Score trung bình test; DeepSeek-R1 khoảng 69,2%. Con số từ abstract và bảng có thể khác do làm tròn.

**Liên hệ repo này:** Đây là benchmark gần nhất về domain và phiên bản MIMIC. Nhưng ứng dụng hiện dùng PostgreSQL và subset khoảng 500 bệnh nhân; không thể lấy gold BigQuery chạy nguyên trạng hay so sánh điểm với paper nếu chưa chuyển dialect, bảo toàn schema/dữ liệu và dùng đúng scorer. Có thể học cách đánh giá cohort, temporal logic, ICD và rubric theo yêu cầu lâm sàng mà không nhập dữ liệu benchmark vào runtime ứng dụng.

## 2. SDE-SQL — ACL 2026

**Bài báo:** [SDE-SQL: Enhancing Text-to-SQL Generation in Large Language Models via Self-Driven Exploration with SQL Probes](https://aclanthology.org/2026.acl-long.116/) ([PDF](https://aclanthology.org/2026.acl-long.116.pdf)). **Nguồn chính thức:** [GitHub Lancelot-Xie/SDE-SQL](https://github.com/Lancelot-Xie/SDE-SQL).

SDE-SQL là **phương pháp inference**, không phát hành benchmark lâm sàng riêng. Phương pháp liên kết entity với giá trị/cột, giữ schema mềm: cột được chọn có mô tả và ví dụ giá trị đầy đủ, cột khác vẫn có tên/kiểu. Model tạo các **SQL probe** để thử cột đích và từng điều kiện, sau đó thử tổ hợp điều kiện trước khi sinh SQL cuối. Khi sửa truy vấn, hệ thống dùng SQLGlot tách AST thành các sub-SQL để chẩn đoán nguyên nhân và tạo probe thử phương án sửa. Generation chính là zero-shot theo nghĩa không dùng cặp hỏi–SQL làm demonstration, dù các công đoạn liên kết entity có prompt few-shot. Bài báo còn dùng self-consistency dựa trên kết quả thực thi của nhiều SQL.

Đánh giá chủ yếu trên **BIRD dev**, thêm Spider; metric là execution accuracy (EX). BIRD có database SQLite đa lĩnh vực và giá trị bẩn, khác MIMIC. Bảng kết quả BIRD dev: Qwen2.5-72B-Instruct 60,17%; SDE-SQL cùng backbone 67,67%; phiên bản thêm SFT 68,19%. 67,67 trừ 60,17 là **7,50 điểm phần trăm**; abstract nói tăng **8,02% tương đối** nên không được tự đồng nhất hai phép so sánh này. Báo cáo độ trễ trung bình 35,19 giây/câu trên BIRD dev ở thiết lập local vLLM. Repo có `src/` inference/evaluation, `run/` script BIRD/Spider, yêu cầu chuẩn bị dữ liệu benchmark ngoài repo và chỉnh đường dẫn trước khi chạy `bash run/run_qwen_eval_template.sh`, sau đó `bash run/run_eval.sh`.

**Liên hệ repo này:** SQL probe có thể bổ sung kiểm chứng schema/value trước generation hoặc chẩn đoán SQL sai. Nhưng trong MIMIC, kết quả rỗng là hợp lệ ở nhiều câu; không được mặc định sửa điều kiện chỉ để có dòng dữ liệu. Probe cần read-only, timeout, giới hạn dòng và chính sách không gửi dữ liệu bệnh nhân chi tiết lên model. Lợi ích BIRD không chuyển thẳng thành hiệu quả MIMIC.

## 3. MAC-SQL — COLING 2025

**Bài báo:** [MAC-SQL: A Multi-Agent Collaborative Framework for Text-to-SQL](https://aclanthology.org/2025.coling-main.36/) ([PDF](https://aclanthology.org/2025.coling-main.36.pdf)). **Nguồn chính thức:** [GitHub wbbeyourself/MAC-SQL](https://github.com/wbbeyourself/MAC-SQL).

MAC-SQL là **framework nhiều agent**: Selector chọn sub-database, Decomposer lập lời giải/sinh SQL bằng few-shot chain-of-thought, Refiner sửa SQL theo phản hồi công cụ. Selector và Refiner được gọi khi cần. Tác giả dùng GPT-4 cho framework và còn fine-tune SQL-Llama từ Code Llama 7B bằng dữ liệu instruction riêng; kết quả SQL-Llama không đại diện cho phiên bản không huấn luyện.

Benchmark là **BIRD và Spider**. Trên BIRD, MAC-SQL+GPT-4 đạt EX 59,39% dev, 59,59% test; VES 66,39% dev, 67,68% test. Trên Spider, EX 86,75% dev và 82,80% test. Ablation BIRD dev khi bỏ Selector/Decomposer/Refiner lần lượt còn 57,28%/55,54%/54,76% so với 59,39%. Repo chứa `core/agents.py`, `core/chat_manager.py`, prompt/config, `run.py`, script đánh giá BIRD/Spider và script huấn luyện SQL-Llama. README yêu cầu Python 3.9, `openai==0.28.1`, dữ liệu BIRD/Spider tải riêng; repo này là code thời điểm paper nên có thể cần điều chỉnh API/model để chạy lại ngày nay.

**Liên hệ repo này:** Pipeline MIMIC hiện đã có retrieval/schema selection, decomposition, validation/repair và candidate selection, nên sao chép nguyên MAC-SQL sẽ trùng chức năng. Có thể đối chiếu ranh giới trách nhiệm của ba agent và thiết kế ablation nội bộ. Không thể lấy điểm BIRD/Spider của paper làm baseline trực tiếp cho 180 câu tiếng Việt hoặc MIMIC Mini.

## Kết luận áp dụng

1. **CLINSQL** là nguồn đánh giá lâm sàng phù hợp nhất về MIMIC-IV v3.1, nhưng đòi BigQuery và toàn bộ dữ liệu/protocol gốc để so điểm.
2. **SDE-SQL** gợi ý công cụ probe trước/sau generation; nên thử nghiệm riêng với guardrail PostgreSQL và phép đo chi phí/độ trễ.
3. **MAC-SQL** là đối chiếu kiến trúc; các thành phần chính đã có tương đương ở mức chức năng trong pipeline hiện tại, nhưng chưa có bằng chứng đạt chất lượng tương đương.

Không có phép so sánh trực tiếp giữa 74,67% CLINSQL Execution Score, 67,67% BIRD EX của SDE-SQL và 59,59% BIRD test EX của MAC-SQL: dataset, model, split và metric khác nhau.
