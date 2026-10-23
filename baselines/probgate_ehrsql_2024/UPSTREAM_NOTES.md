# Mức độ trung thực với nguồn và các điểm chưa được công bố

## Phần đã giữ nguyên

- 52 file tracked được xuất bằng `git show <commit>:<path>`, không lấy `.git` hoặc các file ngoài commit. Một số `.pyc` trong `__pycache__` đã được tác giả track nên vẫn được giữ để checksum đúng; adapter không import những file này.
- Source ProbGate pin `2dcc2230ea049e7fb87160df922933b4ae2645b9`.
- Dataset train/dev/test và database giữ bản tác giả. Gold dev/test lấy từ EHRSQL lịch sử sau khi so khớp đủ từng ID và câu hỏi; source manifest lưu commit đầy đủ.
- Không chạy notebook, không deserialize pickle, không gọi API, không train model ở bước chuẩn bị.
- Source gốc có thể không chạy trực tiếp; đây là bản tham chiếu nguyên trạng. Adapter mới được tách rõ, không sửa source để che khác biệt.

## Thiếu artifact khiến không thể cam kết lặp lại toàn bộ điểm chỉ bằng model note

1. Không có fine-tuned checkpoint T5 generator/T5 classifier, cũng không có output dev của toàn bộ baseline.
2. GPT fine-tuned ID thuộc tài khoản tác giả; notebook không cung cấp weights hoặc một endpoint công khai cho người khác dùng.
3. Không xác định được script/prompt đầy đủ của GPT answerability classifier. Classifier predictions cũng không có.
4. Code có các cấu hình bị gán đè; paper không pin đầy đủ hyperparameters, seed/split/checkpoint cho từng dòng.
5. Artifact `train_schema_dict.json`, `valid_schema_dict.json`, `test_schema_dict.json` được dataset loader đọc nhưng không có trong source tracked.
6. Tên T5-small trong bảng và Flan-T5-small trong source cần được xác minh; không tự đồng nhất.

Do đó, 4 nhánh test có cache để chuyển sang replay; 7 nhánh dev đã được khai báo đầy đủ, bảo toàn source và adapter xử lý nhưng còn cần đầu ra/checkpoint tương ứng. Chưa gọi đây là đã tái lập được kết quả của cả 11 nhánh. Không dùng cùng một cache GPT test để giả làm kết quả T5 hoặc dev.

## Các vấn đề trong source gốc cần xử lý trước khi train/inference

- `t5_model_eval.py` có dòng notebook `!zip` trong file `.py`.
- `t5_model_train.py` tải checkpoint với tên hard-code trước bước training, kể cả khi `RUN_TRAIN=True`.
- Một số lời gọi `T5Dataset` truyền `answerable_or_not_binary`, trong khi constructor nhận `binary_classification`.
- Một số đoạn evaluation sau filtering so trực tiếp chuỗi SQL với nhau thay vì kết quả thực thi. Adapter `score` giữ đường chấm dựa trên thực thi của script scoring riêng, không lấy đoạn này làm bằng chứng EX.
- `.env` chứa đường dẫn local không được tác giả cung cấp; requirements không bao phủ đầy đủ mọi import, ví dụ transformers/scikit-learn/sentence-transformers/python-dotenv.
- `schema.txt`/`schema_tokens.txt` ở root của repository, trong khi script dùng đường dẫn tương đối ở working directory. Không tự chạy tất cả script từ `src/` và giả định đường dẫn đúng.
- `apply_null.py` có tác vụ I/O ở top-level; adapter không import file đó để tránh chạy ngoài ý muốn.

Đây là hạn chế của source công khai, không phải lý do để thay kiến trúc bằng baseline của dự án chính. Sửa runtime trong tương lai phải có patch riêng và ghi thay đổi, thay vì sửa `upstream/`.

## Các chi tiết thuật toán được phân biệt rõ

- Paper dùng ký hiệu threshold `t=425/450/387`; notebook dùng biến `threshold` cho rank index và `k=10` cho số token thấp nhất. README tác giả dùng tên biến không đồng nhất. Gói dùng `rank_index` và `bottom_n` để tránh đảo hai tham số, giữ đúng phép tính notebook.
- Notebook dùng rank zero-based và phép `<=`; tie không bị phá bằng random.
- `get_threshold` gốc có quy tắc chọn index `idx-1`. Không sửa ngầm quy tắc này hoặc tự dùng threshold từ gold dev/test trong adapter. Runtime calibration chưa được chạy.
- GEF gốc lọc thêm kết quả rỗng ngoài lỗi thực thi. Trong helper tác giả, kết quả thành công là list nên phép `"error" in result` không phải tìm substring trong mọi giá trị trả về; adapter giữ phân biệt này.
- Helper scorer ProbGate sắp xếp toàn bộ hàng raw, trong khi scorer EHRSQL chuẩn hóa số 3 chữ số và cắt 100 hàng. Sau kiểm chứng ngày 23/10/2026, adapter mặc định dùng `official`; `author` giữ riêng để đối soát. Hai ID `ab2159e2914558a41cd56bff` và `5a67eba88dd963170a026d15` cho gold số/pred chuỗi số: helper raw chấm sai, official chấm đúng. Vì vậy không dùng helper raw làm protocol chính để so nhánh GPT FT với paper.
- Chấm RS dùng kết quả thực thi, không dùng exact string SQL. VSR/EX không phải metric chính của hai bảng paper.
- Adapter thêm kiểm tra đủ ID, không ghi đè output và SQLite read-only/timeout. Đây là ràng buộc vận hành mới; các timeout phải được báo cáo khi chạy.

## Trạng thái thực thi

Ngày 19/10 chỉ chuẩn bị/hash/unit test. Ngày 23/10 đã chuyển sang kiểm chứng SQL và chấm cache thật; xem `FINAL_RUN_REVIEW.md` và `runs/audit_20261023_docker`. Không train lại hoặc inference lại GPT/T5. Điểm trong `configs/experiments.json` luôn là `published_scores`, không thay bằng kết quả replay.
