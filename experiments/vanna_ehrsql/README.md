# Hệ thống thứ ba: Vanna AI trên EHRSQL

**Yêu cầu cuối cùng ngày 27/10/2026:** train 5.124 câu chỉ làm knowledge base; **chỉ sinh SQL và đánh giá 1.167 câu test**, bỏ dev. Dùng key Groq đã cấu hình và `qwen/qwen3.8-27b`. Primary cố định là `vanna`; `vanna_gef` là nhánh phụ. Hai prediction train phát sinh trước khi làm rõ đã dừng và bị loại khỏi đánh giá. Xem `STATUS.json`, `LATEST_RESULTS.json` và `RESULTS.md` khi lượt chạy được chấm.

Vanna là **framework Text-to-SQL/RAG**, không phải một LLM riêng. Thí nghiệm này dùng luồng SQL/RAG legacy có sẵn trong package **Vanna 2.0.2**, với index Chroma độc lập. Không gọi nó là agent Vanna 2.0 đầy đủ: không chạy web UI, chart, conversation, tools đa lượt hoặc sinh câu trả lời tự nhiên. Chỉ so phần English → SQL bằng benchmark EHRSQL.

## Ba hệ thống để đối chiếu

1. `../../baselines/probgate_ehrsql_2024`: hậu xử lý và chấm lại **SQL/logprobs đã công bố của tác giả**. Không có model fine-tuned riêng của tác giả để sinh SQL mới.
2. `../apply_my_work_to_baseline`: phương pháp đề xuất, gồm các nhánh RAG, rewrite tùy chọn, sửa SQL và lọc.
3. Folder này: `VannaBase.generate_sql()` + `ChromaDB_VectorStore` của Vanna, có adapter LLM và định dạng đầu ra EHRSQL.

Mọi hệ thống dùng cùng database 17 bảng, câu hỏi dev/test và scorer official. Để chứng minh đóng góp phương pháp giữa Vanna và hệ thống đề xuất, dùng cùng LLM, generation settings và báo tài nguyên. So với paper fine-tuned là so kết quả hệ thống, không cô lập được ảnh hưởng của model.

## Cấu hình đã chuẩn bị

- Framework: `vanna==2.0.2`, wheel cố định SHA256, cài trong `.vendor/`; không thay site-packages ứng dụng chính.
- Database: snapshot SQLite EHRSQL/ProbGate hiện có, không sao chép hoặc dựng database khác.
- Corpus: 5.124 cặp hỏi/SQL train, gồm 450 ví dụ `null`; 17 DDL và một tài liệu quy ước benchmark. Không index gold dev/test.
- Embedding: `paraphrase-multilingual-MiniLM-L12-v2` đang có cache cục bộ, CPU, không gọi API embedding. Chọn cùng embedding với hệ thống đề xuất để giảm một nguồn khác biệt.
- Vanna retrieval: bốn ví dụ SQL, 17 DDL, một tài liệu. SQL examples được Vanna embed theo JSON question+SQL, khác với cách chỉ embed câu hỏi của hệ thống đề xuất; đây là hành vi Vanna gốc.
- Dùng prompt assembly và SQL extraction gốc. Thêm output contract để đáp án không có thông tin là `null`, vì hướng dẫn Vanna gốc yêu cầu giải thích bằng văn bản. Ghi rõ đây là **Vanna cấu hình cho EHRSQL**, không phải mặc định chưa cấu hình.
- `allow_llm_to_see_data=False`; không gửi hàng kết quả bệnh nhân cho LLM. Thực thi SQLite chỉ đọc để chấm, không gửi lỗi trở lại Vanna để sửa.
- `generate_sql()` một lượt gọi; không gọi `ask(auto_train=True)`. Prediction dev/test không được thêm vào index.
- Nhánh `vanna` là Vanna thuần theo cấu hình trên. Nhánh `vanna_gef` dùng lại SQL rồi lọc lỗi/kết quả rỗng, là hậu xử lý bổ sung để đối chiếu cùng GEF; **không phải tính năng Vanna mặc định và không phải ProbGate đầy đủ**.

Vanna gọi nạp schema/ví dụ là “train”. Ở đây đó là xây kho retrieval; **không fine-tune trọng số model**. Bulk loader giữ nguyên format và ID tài liệu của các hàm `vn.train(...)` gốc, chỉ batch embedding/storage để chuẩn bị nhanh hơn.

## Trạng thái model

Lượt chạy hiện tại chọn `qwen/qwen3.8-27b` qua Groq. Runner dùng lại **transport Groq** để accounting/cache/quota, không dùng RAG hoặc prompt của hệ thống đề xuất. Cần adapter khác trước khi dùng Gemini/DeepSeek/GPT; không chỉ thay tên model vào Groq. Không tự đổi model khi chạm quota.

## Chuẩn bị và chạy

Từ thư mục gốc dự án, cài runtime riêng nếu chưa có:

```powershell
.\experiments\vanna_ehrsql\setup.ps1
.\.venv\Scripts\python.exe -X utf8 -B experiments/vanna_ehrsql/prepare.py --build-index
```

Hai bước này chỉ tải package công khai và tạo embedding cục bộ; không gọi API LLM. Runtime dùng các dependency nền trong `.venv` hiện tại; `requirements-support.txt` cố định các package còn thiếu trong `.vendor`.

**Lệnh dưới chỉ chạy sau khi đã quyết định model và chi phí.** Thay `MODEL_ID` bằng cùng model đã chọn cho hệ thống đề xuất:

```powershell
.\.venv\Scripts\python.exe -X utf8 -B experiments/vanna_ehrsql/run.py --run-name vanna_dev_01 --split dev --model MODEL_ID --limit 100
.\.venv\Scripts\python.exe -X utf8 -B experiments/vanna_ehrsql/score.py --run-name vanna_dev_01
```

Chọn số ví dụ, model, token budget và primary trên dev; dùng run name mới nếu code/config thay đổi. Để chạy full dev, dùng `--limit 0`. Sau khi cố định, chạy đủ 1.167 câu test và chỉ định primary đã chọn:

```powershell
.\.venv\Scripts\python.exe -X utf8 -B experiments/vanna_ehrsql/run.py --run-name vanna_test_01 --split test --model MODEL_ID --primary-variant vanna --limit 0
.\.venv\Scripts\python.exe -X utf8 -B experiments/vanna_ehrsql/score.py --run-name vanna_test_01
.\.venv\Scripts\python.exe -X utf8 -B experiments/vanna_ehrsql/compare.py --vanna-run vanna_test_01 --our-run OUR_COMPLETE_TEST_RUN
```

Không tăng điểm bằng cách chọn primary trên test. So sánh cuối từ chối báo cáo thiếu ID hoặc khác scorer. `compare.py` dùng primary của mỗi run, ghi rõ model có trùng nhau hay không, tạo JSON ba hệ thống và khoảng tin cậy paired cho chênh lệch RS10. Những run còn dở có thể chấm để chẩn đoán, nhưng không so với điểm toàn bộ paper.

Lệnh đang dùng để chạy/resume **chỉ test**, giữ nguyên config đã cố định:

```powershell
.\experiments\vanna_ehrsql\run_test.ps1
```

Lệnh này không sinh prediction train. Nếu bị quota chặn, giữ checkpoint và chấm đúng số câu test đã hoàn tất. Gold test chỉ được nạp sau khi giai đoạn gọi model đã dừng. `RESULTS.md` gắn nhãn PARTIAL nếu chưa đủ 1.167 câu. Chạy lại cùng lệnh khi quota sẵn có để resume, giữ nguyên code/config. Đổi code/model phải dùng run name mới. `run_both.py` được giữ để truy vết lượt chạy cũ, không phải workflow được yêu cầu hiện tại.

## Metric và output

`score.py` dùng lại đúng evaluator official đang dùng cho hệ thống đề xuất: RS0/RS5/RS10/RSN, answerable EX, VSR thực thi, breakdown câu sai/từ chối và token usage. Từ chối đúng câu unanswerable được tính trong RS; không phải đúng SQL trong EX. VSR ở đây là metric vận hành tự báo cáo, không gọi là VSR công bố của ProbGate.

Kết quả bị cắt token, lỗi API/quota, hoặc thiếu prediction không được biến âm thầm thành `null`. Output thô, SQL, finish status qua cache, hash request, model config và source hashes được giữ để đối soát. GEF là nhánh riêng.

Các file chính: `benchmark.py`, `vanna_adapter.py`, `prepare.py`, `run.py`, `score.py`, `compare.py`. `PREPARATION_STATUS.json` ghi tình trạng index thật; `SOURCE.md` ghi phiên bản/link; `tests/test_vanna.py` kiểm tra luồng Vanna bằng transport giả, không phải kết quả benchmark.

Chỉ dùng các điểm ghi trong report sau thực thi. Không gán điểm paper cho Vanna, không đặt điểm giả hay dùng cache tác giả làm prediction của Vanna.
