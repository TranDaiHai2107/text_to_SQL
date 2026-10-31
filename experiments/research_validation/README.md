# Xác nhận nghiên cứu cho V5 đã chốt

V5 giữ nguyên tại `experiments/ours_improved_v5`. Thư mục này chỉ tạo đối chứng, ablation, kiểm tra dữ liệu mới và chấm điểm. Không chọn lại policy, không đổi model hoặc fine-tune, không sửa output/gold/scorer để tăng điểm. RS10 cũ 74,89 vẫn là kết quả exploratory; không đổi tên thành holdout độc lập.

## Thiết kế đã khai báo

`protocol.json` là đặc tả máy đọc được. `V5_LOCK.json` khóa SHA-256 của source phụ thuộc, database, scorer, policy và output lịch sử; `PROTOCOL_LOCK.json` khóa cả giao thức và code suite này. Đây là đăng ký nội bộ có thể kiểm tra, chưa phải preregistration có dấu thời gian của bên thứ ba. Không tự push, công bố hoặc commit.

Ba gia đình generation dùng cùng DeepSeek Flash, knowledge train+dev 6.287 câu, ba route, hai route không thinking cap 2.048 và một route thinking cap 4.096. Mỗi route được tối đa một lần sửa lỗi schema/thực thi. Chúng có cùng **trần generation**, không mặc nhiên có cùng chi phí: số token input/output, model version/fingerprint và thời gian từng gia đình được ghi riêng.

- `ours_structured`: generation V3 nguyên bản, sau đó V5 nguyên bản.
- `control_dense`: chỉ thay cơ chế chọn ví dụ bằng dense top-4 + top-2 null; giữ schema, catalog, prompt, generation và V5 postprocessing. Kiểm tra đóng góp reranker ví dụ, không gọi đây là bỏ hết RAG.
- `control_vanna`: retrieval/prompt/extraction của Vanna với envelope ba route và bộ chọn đồng thuận chung. Phải ghi **Vanna augmented**, không gán kết quả đó cho Vanna mặc định. Vanna native một lượt được giữ làm tham khảo thực tế.

Bảy nhánh chấm dùng lại generation trong mỗi gia đình. Không cộng token nhiều lần cho các ablation dùng chung output. Primary contrast cố định `v5_full - vanna_matched_three`; bốn đối chiếu secondary có Holm correction. Ba replicate trong cache riêng; không chọn seed tốt nhất và không dừng khi đạt điểm mục tiêu. Các cấu hình postprocessing chạy trên cùng candidate để cô lập đóng góp tốt hơn việc đổi model.

## Việc đã làm được ngay

Chạy ablation offline trên đủ 1.167 test cũ bằng output đã lưu, không gọi API. Gỡ guard direct, so direct với three-route, so normalization V4 với raw và compiler V5 với V4. Không thể suy ra ablation retrieval từ SQL cache; cần generation mới trên tập xác nhận phù hợp.

```powershell
.venv/Scripts/python.exe experiments/research_validation/freeze_v5.py
.venv/Scripts/python.exe experiments/research_validation/seal_protocol.py
.venv/Scripts/python.exe experiments/research_validation/replay_ablation.py
.venv/Scripts/python.exe experiments/research_validation/run_confirmatory.py
```

File offline: `runs/exploratory_20261029/ablation.json`. Đây không phải kết quả xác nhận. Không thực hiện kiểm định confirmatory trên test đã dùng để phát triển.

Kết quả đã chạy ngày 29/10/2026 trên đủ 1.167 câu, không gọi API mới:

- Direct trước guard: RS10=24,94; 79 câu sai.
- Direct sau guard V3: RS10=49,36; 52 câu sai.
- Đồng thuận ba route thô: RS10=71,21; 21 câu sai.
- Round3 + dictionary guard V4, chưa compiler: RS10=73,09; 21 câu sai.
- V5 đầy đủ: RS10=74,89; 21 câu sai.
- Canonical direct V5: RS10=54,16; 47 câu sai; đây là một route sau canonicalization, khác direct V3.

Guard là cả gói lọc GEF/hard-contract; normalization V4 cũng là cả gói fingerprint/dictionary guard. Không gán toàn bộ chênh lệch cho chỉ một dòng xử lý. So sánh direct với ba route có khác ngân sách generation. So V4 với V5 dùng cùng bộ ba candidates và policy đồng thuận, là đối chiếu rõ nhất cho compiler trong dữ liệu đã đo. Compiler khôi phục thêm 21 câu đúng, không giảm 21 câu sai còn lại. Cả sáu kết quả đều exploratory.

## Dữ liệu xác nhận là điều kiện còn thiếu

Tất cả 5.124 train + 1.163 dev đã vào knowledge, 1.167 test đã được xem điểm. Không có tập nào trong ba split này đủ điều kiện tự động gọi là dữ liệu mới cho V5. Chia lại hoặc đổi ID không giải quyết việc đã tiếp xúc dữ liệu. Raw MIMIC khác cũng chưa phải bộ câu hỏi–SQL có nhãn.

Một tập mới cần: câu hỏi tiếng Anh, gold SQL hoặc `null`, nguồn/version và bằng chứng nhãn được kiểm định, xác nhận chưa dùng để thiết kế, cluster template/family do nguồn dữ liệu hoặc người có năng lực xác nhận. Nhãn từ benchmark chính thức không cần team tự thuê bác sĩ chấm lại; nhưng tự tạo nhãn thì chạy SQL thành công không đủ để xác nhận SQL diễn đạt đúng câu hỏi, và `null` đúng về mặt ngữ nghĩa.

Intake chặn trùng ID/câu hỏi chuẩn hóa với **cả ba split cũ**, chặn near-duplicate token Jaccard ≥0,85, cần cả answerable/unanswerable và ít nhất 30 cluster. Ngưỡng 30 chỉ là guard vận hành, không bảo đảm statistical power. Nhãn, đáp án và flag answerability bị loại khỏi input inference. Source và output intake khóa hash; kiểm tra máy không chứng minh tuyệt đối độc lập hoặc không có dữ liệu trong pretraining.

Nguồn mở rộng đã kiểm tra: [EHRSQL NeurIPS 2022](https://papers.neurips.cc/paper_files/paper/2022/hash/643e347250cf9289e5a2a6c1ed5ee42e-Abstract-Datasets_and_Benchmarks.html), [repo tác giả](https://github.com/glee4810/EHRSQL). Repo có MIMIC-III/eICU và thông báo bản 1.5.0 năm 2026. Đây là **ứng viên đánh giá chuyển miền**, chưa đăng ký làm holdout: khác schema/clock, cần adapter được kiểm tra và audit trùng template/câu hỏi với EHRSQL 2024 trước. Frozen V5 không tự hỗ trợ các database đó. Không lấy điểm trên tập này so trực tiếp 74,21 của ProbGate trên MIMIC-IV.

Đã tải vào vùng cách ly đúng commit `01241a3c55bda895561c76923251ea2421d2e892`: README/changelog/tables và hai test. Chỉ kiểm tra metadata/câu hỏi, chưa kiểm tra lỗi SQL hoặc gọi model trên nguồn mới; chưa tải database. Xem `EXTERNAL_DATA_AUDIT.json` để có URL và hash từng file:

- MIMIC-III: 1.786 câu, gồm 1.198 answerable và 588 unanswerable; 130 câu trùng chuẩn hóa với dữ liệu cũ, 210 câu có Jaccard token ≥0,85. Có 167 q_tag cho answerable; 588 câu unanswerable thiếu q_tag.
- eICU: 1.792 câu, gồm 1.204 answerable và 588 unanswerable; 48 câu trùng chuẩn hóa, 67 câu có Jaccard token ≥0,85. Có 165 q_tag cho answerable; 588 câu unanswerable thiếu q_tag.

Các số trùng ở từng phép kiểm tra có thể chồng lấn, không cộng lại để tính số câu loại. Dù không trùng ID, vẫn trùng câu hỏi; chỉ đổi dataset/domain không đủ để chứng minh độc lập. `DATASET_INVENTORY.json` là ảnh chụp inventory local trước khi tải ứng viên; `EXTERNAL_DATA_AUDIT.json` là bước audit bên ngoài tiếp theo. Hai nguồn vẫn chưa đủ điều kiện của protocol MIMIC-IV hiện tại. Nếu dùng để xác nhận chuyển miền, cần đăng ký protocol/adapter riêng trước khi chạy, giữ nguyên V5 gốc và báo cáo overlap rõ ràng.

17 unit test mới đã qua. Integration smoke với index thật xác nhận 6.287 ví dụ, bảy arm được tạo, V5 lựa chọn đúng SQL đã đóng băng trong ca kiểm tra; không dùng model giả để báo điểm thực nghiệm và không gọi API trong bước smoke.

## Hợp đồng intake và chạy sau khi có dữ liệu đủ điều kiện

`inputs.json`: list record gồm `id`, `question`, `cluster_id` (cùng template phải cùng cluster, không dùng ID duy nhất để giả lập cluster).

`gold.json`: mapping cùng toàn bộ ID tới một SQL hoặc đúng chuỗi `null`.

`provenance.json`: `source`, `version`, `independence_statement`, `annotation_evidence`, `cluster_evidence` là chuỗi có thông tin thật; `not_used_for_method_design`, `English_questions`, `cluster_ids_reviewed` là true; `annotation_validation` là `official_release` hoặc `documented_human_review`. Không điền true nếu chưa có bằng chứng. Runner hiện yêu cầu đúng database MIMIC-IV đã pin; không tự sửa SQL/gold để làm tương thích.

```powershell
.venv/Scripts/python.exe experiments/research_validation/register_dataset.py --name NEW_DATA --inputs PATH_TO_INPUTS --gold PATH_TO_GOLD --provenance PATH_TO_PROVENANCE
.venv/Scripts/python.exe experiments/research_validation/run_confirmatory.py --dataset NEW_DATA
.venv/Scripts/python.exe experiments/research_validation/run_confirmatory.py --dataset NEW_DATA --replicate 1 --execute
.venv/Scripts/python.exe experiments/research_validation/run_confirmatory.py --dataset NEW_DATA --replicate 2 --execute
.venv/Scripts/python.exe experiments/research_validation/run_confirmatory.py --dataset NEW_DATA --replicate 3 --execute
.venv/Scripts/python.exe experiments/research_validation/score_confirmatory.py --dataset NEW_DATA
```

Không gọi API khi chỉ preflight. Chưa có tập mới thì state `awaiting_new_eligible_dataset`; không tạo test giả để vượt qua gate. Inference có checkpoint từng gia đình và câu hỏi, không đọc gold, không pad API failure thành null. Scorer tách riêng và đòi đủ mọi câu, mọi nhánh, cả ba replicate trước khi đọc gold. Replicate tăng kiểm tra ổn định API; không làm tăng số câu độc lập. Bộ chấm dùng core official đã đối chiếu Docker trong V5; các thí nghiệm mới chạy core trên host, không tự gán nhãn Docker verified nếu chưa đối chiếu riêng.

## Điều kiện kết luận

Metric chính RS10; chênh lệch trung bình qua ba replicate. Bootstrap và randomization ghép cặp theo cluster, không coi các lần gọi API cùng câu là dữ liệu độc lập. Positive primary chỉ khi delta >0, CI95 lower bound >0 và p two-sided <0,05, trên dữ liệu được đăng ký đúng. Ngược lại báo inconclusive/negative; không đổi metric/subset/policy. Báo cáo EX, coverage, số lỗi, RSN và chi phí dù bất lợi. Tính mới và giá trị ứng dụng vẫn cần lập luận; một p-value không tự chứng minh novelty.

Đây chỉ là English→SQL; không xác nhận ASR, dịch tiếng Việt, SQL→text hoặc tính an toàn lâm sàng.
