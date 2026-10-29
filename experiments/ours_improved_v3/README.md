# V3 — SQL candidates, shared benchmark conventions and dev-only risk selection

Tiếp tục riêng hệ thống đề xuất. Không chạy lại tác giả/Vanna, không thay đổi kết quả v1/v2, không fine-tune LLM. English → SQL trên database SQLite EHRSQL 2024 đã pin; phần ứng dụng tiếng Việt/PostgreSQL chưa được chuyển cấu hình bằng thí nghiệm này.

## Thay đổi

- Mở rộng catalog thành giá trị gắn với đúng bảng/cột, gồm cost.event_type, vị trí/loại nhập viện, careunit, đường dùng thuốc. Top-K không phải danh sách đầy đủ để kết luận thiếu dữ liệu.
- Rerank ví dụ bằng masked question, loại câu hỏi và cấu trúc AST của SQL knowledge. Giữ full schema17bảng. Đây là adaptation, không gọi là tái hiện nguyên DAIL-SQL.
- Dùng cùng quy ước thời gian, visit, ties, đơn vị và số cột output cho mọi đường sinh. Quy tắc có train/dev evidence; không mã hóa ID/đáp án test vào prompt.
- A/direct và B/structural dùng DeepSeek Flash thinking disabled, tối đa2048token. C/plan dùng cùng model nhưng thinking enabled, tối đa4096token. Đây là khác biệt inference compute phải báo, không gán toàn bộ cải thiện cho retrieval.
- Không có reviewer tự do sửa SQL đang thực thi được. Chỉ sửa tối đa một lần khi parse/schema/execution thất bại. Giữ mọi ứng viên; GEF lỗi/rỗng/hard-constraint là bước riêng có dấu vết `pre_guard_sql`/`pre_guard_execution`.
- So kết quả đầy đủ bằng fingerprint có kiểu, số cột, NULL và duplicate rows; không dùng cap100/round3 của scorer để tạo bằng chứng đồng thuận. SQL lỗi/rỗng và request trùng cache không tạo phiếu đồng thuận. Cùng kết quả trên một database vẫn có thể cùng sai.
- Bảy policy được khai báo trước: A+guard, hai ứng viên đồng thuận, đa số2/3, execution+structure, cả3đồng thuận, loại trivial scalar, đồng thuận không có soft issue. Chọn bằng RS10 trên tuning dev, coverage tối thiểu35%.

## Quy trình nghiên cứu

400câu dev mới được chọn cố định:300tune+100audit, phân tầng80/20answerable/unanswerable; không trùng300câu calibration cũ hoặc dev evidence dùng viết quy ước. Toàn bộ400ID và câu trùng nội dung bị loại khỏi mọi RAG example/null-neighbor khi phát triển. Đây là question holdout; không tuyên bố template-family holdout.

Sau khi chọn policy trên300câu, khóa hash policy rồi mới chạy100audit. Không chọn lại policy từ audit. Final test dùng toàn bộ train+dev6.287câu như yêu cầu; cần ghi rõ index khác với lúc calibration. Không tuyên bố bảo đảm conformal.

Test1.167câu đã được xem ở các vòng trước. V3 là cải thiện exploratory có tham khảo test trong thiết kế; không biến nó thành holdout độc lập bằng đổi tên folder hay seed. Các vòng chỉnh sửa được chọn bằng dev, không chạy test liên tục rồi chỉ giữ điểm tốt nhất.

Protocol chứa hash nguồn, DB, scorer, ID partition, model settings và grid. API cache/checkpoint từng câu cho phép tiếp tục sau quota/network. Lỗi API dừng; không padding câu chưa chạy thành null. Log không lưu API key, reasoning_content hay kết quả bệnh nhân gửi vào model. Route metrics là các nhánh **đã guard/GEF**, không phải raw generation.

## Chạy

Từ root dùng `.venv/Scripts/python.exe experiments/ours_improved_v3/run_v3.py --run-name NAME --phase tune --workers 8`, sau đó `--phase audit` và `--phase test` với cùngNAME. `--phase all` chạy theo thứ tự tune→freeze→audit→test. `--max-questions 5` chỉ chạy thử có checkpoint, không chấm thành kết quả đủ split.

Key lấy từ `.env`; không truyền qua CLI. Không tự nạp tiền/chuyển model khi tài khoản hết credit. Folder runs bị ignore bởi Git.

`deepseek_flash_v3_20261029_dev1` là smoke5câu. `deepseek_flash_v3_20261029_r1` kế thừa cache smoke sau khi sửa nhãn provenance của guard-null và kiểm tra hash audit; generation không đổi.

Lần r1 gặp transient Windows lock khi thay `STATUS.json`: master ghi164checkpoint rồi dừng, nhưng worker đã hoàn thành các request còn lại vào cache/staged. Lần chính **`deepseek_flash_v3_20261029_r2`** khôi phục đủ300record hoàn tất, thêm bounded retry và xem status là metadata không quyết định kết quả. Không đổi prompt/model và không trả phí lại request đã có cache. Đã tái tạo và xác minh hash900request ban đầu của300câu tuning theo prompt hiện tại.

42kiểm tra tự động đã qua trước audit/test, gồm chống leakage, guard-null, quorum, thinking cache key, provider failure và Windows metadata lock. Policy chọn từ300tune là `strict_three_agree` (RS10=88,00; coverage71,67%);100audit giữ nguyên policy đạtRS10=85,00. Đây chưa là điểm full test; xem kết quả chính thức sinh ra trong thư mục lần chạy sau khi đủ1.167câu.

## Nguồn phương pháp

- [Nghiên cứu và phân tích lỗi trước triển khai](../../research/TEXT2SQL_IMPROVEMENT_RESEARCH_20261028_VI.md).
- [PromptMind — EHRSQL2024](https://aclanthology.org/2024.clinicalnlp-1.34.pdf): ensemble so kết quả thực thi. Cấu hình khôngFT GPT4+Opus RS10=65,72; không gán số74,89 của ensemble có FT cho cấu hình khôngFT.
- [DAIL-SQL](https://github.com/BeachWang/DAIL-SQL): truy xuất ví dụ/cấu trúc.
- [Confidence Estimation for Text-to-SQL, AAAI2026](https://ojs.aaai.org/index.php/AAAI/article/view/40523): consistency và execution grounding.
- [ProbGate paper](https://aclanthology.org/2024.clinicalnlp-1.65/): RS0=81,92; RS5=78,06; RS10=74,21; RSN=−818,08 là mốc công bố. EX77,73% tính bổ sung từ cache, không phải EX paper công bố. Không gọi lại hoặc tái huấn luyện model fine-tuned của tác giả ở đây.
