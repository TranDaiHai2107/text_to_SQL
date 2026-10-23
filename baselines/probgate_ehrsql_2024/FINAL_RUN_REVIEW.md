# Rà soát code, model và khả năng chạy cuối — 23/10/2026

## Kết luận

**Đã đủ điều kiện chạy lại bốn baseline test bằng cache tác giả.** Đã thực thi đầy đủ 1.167 câu của từng nhánh trong Docker, dùng cả hai scorer riêng để đối soát. Scorer **EHRSQL official** là mặc định cho lần chạy tiếp theo. Đây là tái hiện hậu xử lý/chấm đầu ra công bố; không phải đã tải model GPT fine-tuned, train lại GPT/T5 hoặc đo hệ thống RAG của ứng dụng.

**Chưa đủ điều kiện tuyên bố đã chạy lại toàn bộ 11 model/nhánh hoặc hệ thống của mình tốt hơn paper.** Bảy nhánh dev thiếu checkpoint/output. Ứng dụng chính vẫn hướng tiếng Việt/PostgreSQL; adapter baseline offline chưa gọi RAG của ứng dụng để sinh SQL tiếng Anh trên database EHRSQL/SQLite.

## Kết quả kiểm chứng thực tế

Nguồn điểm công bố: [ProbGate at EHRSQL 2024, Table 2](https://aclanthology.org/2024.clinicalnlp-1.65.pdf). Các số sau là **cache replay thực chạy bằng official scorer**, thứ tự RS(0) / RS(5) / RS(10) / RS(N), làm tròn hai chữ số để đọc:

1. GPT FT: **73.52 / -58.87 / -191.26 / -30826.48**; 858 đúng, 309 sai, 0 từ chối.
2. GPT FT + ProbGate(450): **79.43 / 73.01 / 66.58 / -1420.57**; 927 đúng, 15 sai, 225 từ chối câu answerable.
3. GPT FT + ProbGate(450) + GEF: **79.78 / 75.92 / 72.07 / -820.22**; 931 đúng, 9 sai, 227 từ chối câu answerable.
4. GPT FT + ProbGate(425) + GEF: **81.92 / 78.06 / 74.21 / -818.08**; 956 đúng, 9 sai, 202 từ chối câu answerable.

“Đúng” trong RS gồm cả trả lời đúng câu answerable và từ chối đúng câu unanswerable. Vì vậy RS(0) **không phải EX**. Không có query bị timeout trong lần kiểm chứng này. Lỗi thực thi dự đoán vẫn được giữ trong mẫu số; nhánh GPT FT có 163 lỗi, nhánh ProbGate450 còn 2 lỗi, hai nhánh sau GEF còn 0 lỗi thực thi ở bước score. GEF đã lọc lỗi trước đó, không có nghĩa tất cả SQL còn lại đều đúng ngữ nghĩa.

RS(0) của cả bốn nhánh khớp số công bố khi làm tròn hai chữ số. Cấu hình cuối khớp cả bốn ô ở độ chính xác này. Một số ô khác khác 0.01 ở cách hiển thị: GPT FT RS10/RSN, GEF450 RS10; chênh lệch giữa số thực tính được và số paper ghi đều dưới 0.01 điểm. Giữ nguyên số thực và target, không sửa target hoặc ép số replay về paper. Chưa xác định được chính xác nguyên nhân trình bày các ô này của tác giả.

Bằng chứng trong `runs/audit_20261023_docker/`:

- `preflight.json`: toàn bộ gold test thực thi được.
- Mỗi nhánh có `prediction.json`, `prediction.metadata.json`.
- `scores.json`: scorer helper raw của tác giả, giữ làm đối soát.
- `scores_official.json`: scorer EHRSQL official, dùng làm kết quả chính trong đợt audit này.
- `comparison.json`: đối soát helper raw; `comparison_official.json`: so official với paper, giữ chênh lệch đầy đủ.
- `scorer_diagnostic.json`: kết quả thực thi hai câu làm helper raw khác official.

Các run mới theo script mặc định chỉ có `scores.json` với trường `scorer: official` và `comparison.json`; tên file audit khác vì audit đã chạy tách hai protocol.

## Vì sao đổi scorer mặc định

Helper raw trong repo ProbGate so trực tiếp list các giá trị Python. Hai ID `ab2159e2914558a41cd56bff` và `5a67eba88dd963170a026d15` có gold là số `500.0`/`10.0`, còn prediction là chuỗi `"500.0"`/`"10.0"`. Helper raw chấm sai; official chuẩn hóa chúng về cùng giá trị và chấm đúng. Đây là khác biệt kiểu dữ liệu, không phải lỗi token filtering hoặc timeout.

Helper raw cho GPT FT RS0 = 73.350471; official cho 73.521851, tương ứng paper 73.52. Official dùng stored gold, chuẩn hóa giá trị số ba chữ số và tối đa 100 hàng. Chế độ `author` vẫn tồn tại để bảo toàn source tham chiếu; không trộn hai protocol trong một bảng kết quả.

## Dataset và thuật toán

- SHA256 của snapshot, câu hỏi, gold, database và reserved words đều hợp lệ; không sửa file trong `upstream/`.
- Source pin `2dcc2230ea049e7fb87160df922933b4ae2645b9`; annotation EHRSQL pin `5ddaaa79e6121bf22f808df34166f6f4e03f4c86`.
- Train 5.124, dev 1.163, test 1.167. Database tác giả: 17 bảng, 94 bệnh nhân.
- Toàn bộ 934 SQL gold answerable của test chạy được; 233 gold là `null`; không có gold trả về rỗng hoặc lỗi.
- Đã so hàm tính bottom-10 logprob với hàm gốc trích AST trên **cả 1.167 bản ghi cache**, không có sai khác.
- Rank index zero-based, dấu `<=`, reserved token list và GEF lọc lỗi/kết quả rỗng được giữ. Rank425 từ chối 426 câu trước GEF; rank450 từ chối 451 câu. Không tự sửa thành 425/450 câu.
- Clock `2100-12-31 23:59:00` được thay trong SQL bằng postprocessor gốc; không đổi đồng hồ máy.
- SQLite mount chỉ đọc; root filesystem read-only; network none; user 10001. Base image đã pin digest. Mỗi command ghi provenance code/đầu vào/runtime; không cần cài SDK model trong container.

## Model đã đúng chưa?

**Baseline GPT:** notebook gốc chỉ định base `gpt-3.5-turbo-0125` và fine-tuned model ID riêng tài khoản tác giả; inference temperature 0, logprobs true, top_logprobs 5. Model/checkpoint riêng này chưa tải về hoặc có quyền truy cập. Cache chứa đầu ra của tác giả, đủ cho bốn nhánh test đã kiểm chứng. Đổi sang GPT/Claude/Qwen khác phải ghi là thí nghiệm mới.

**Baseline T5:** large dùng định danh `gaussalgo/T5-LM-Large-text2sql-spider` trong code. Small có khác biệt giữa tên trong paper và `google/flan-t5-small` trong source. Các checkpoint sau fine-tune EHRSQL của generator/classifier và output dev chưa được công bố đủ. GPT classifier cũng chưa có implementation/prompt/output đầy đủ để tái hiện. Không chạy script upstream hàng loạt: còn lỗi cú pháp notebook, cấu hình ghi đè, file schema dictionary thiếu và đường dẫn checkpoint hard-code. Chi tiết: `UPSTREAM_NOTES.md`.

**Ứng dụng chính:** `qwen/qwen3.8-27b` qua **Groq**, không phải xAI Grok. Đã kiểm tra API liệt kê model của tài khoản: có model đang cấu hình; không gọi API sinh nội dung. [Groq hiện liệt kê model này ở nhóm preview](https://console.groq.com/docs/models). Danh sách model xác nhận tên/khả năng liệt kê, không chứng minh độ chính xác hoặc đảm bảo mọi inference sẽ thành công.

**Embedding của ứng dụng:** `paraphrase-multilingual-MiniLM-L12-v2`, dimension384. Tên model/count thực tế của Chroma khớp: ICD3.115, schema31, examples101, examples_eval73. Hash file nguồn schema/examples/eval đều khớp; không cần đổi embedding để chạy cache baseline.

## Lỗi code đã sửa trong đợt rà soát

1. `evaluate.py` trước đây loại lỗi generation/execution khỏi mẫu số EX. Nay mọi câu gold không rỗng đều ở mẫu số; lỗi được tính sai, kể cả đọc lại records cũ có `execution_match: null`.
2. So sánh DataFrame trước đây sắp xếp giá trị bên trong từng hàng, khiến `[1,2]` và `[2,1]` có thể được tính bằng nhau. Nay giữ vị trí cột, duplicate rows và chuỗi chính xác; chỉ bỏ thứ tự hàng/alias. Giữ quy tắc số sáu chữ số của evaluator nội bộ; không đồng nhất nó với scorer EHRSQL.
3. Output ứng dụng ghi `evaluation_version: 2`; UI cảnh báo kết quả cũ. **Phải chạy lại trước khi dùng điểm cũ cho báo cáo.** Empty-gold vẫn được báo riêng/exclude trong evaluator nội bộ, nên không dùng EX đó để so trực tiếp với RS của EHRSQL.
4. Baseline kiểm tra đủ label/answer IDs, answerability, cache shape và logprob hữu hạn; từ chối duplicate T5 IDs, scorer sai hoặc timeout không hợp lệ; giữ đúng cách xử lý GEF khi kết quả không sort được như helper gốc.
5. Script cuối tự build code mới, đợi healthy, chạy gold preflight, không ghi đè run cũ, ghi provenance và tự tạo bảng đối chiếu JSON. Có log tiến độ cho bước score. Không sửa điểm paper trong registry.

Kiểm thử đạt: **13 tests baseline + 16 tests ứng dụng = 29**. Kiểm tra syntax 13 module Python chính/adapter và parser PowerShell đều đạt. Không chạy training hay API sinh nội dung. Endpoint models.list chỉ được dùng để xác nhận model ứng dụng.

## Lệnh chạy cuối

Mở Docker Desktop, từ `D:\Github\text_to_SQL`:

```powershell
.\baselines\probgate_ehrsql_2024\run_cached_baselines.ps1 -Scorer official -RunName final_official_01
```

Đổi tên RunName nếu thư mục đã tồn tại. Script chỉ thao tác service baseline, không cần dựng lại SQLite/PostgreSQL. Sau khi xong, dùng `runs/final_official_01/comparison.json` và bốn `scores.json`. Giữ scorer/model nguồn/cache provenance trong khóa luận.

Để có **kết quả của hệ thống mình** so với paper, bước còn thiếu là sinh prediction cho đủ1.167 ID bằng cấu hình English/EHRSQL/SQLite của hệ thống, có quy tắc từ chối câu unanswerable và retrieval chỉ từ train, rồi chấm bằng cùng official scorer. Không dùng cache tác giả làm output của hệ thống mình, không chọn threshold theo gold test, không so 180 câu nội bộ với Table2.

Tại lúc rà soát chỉ service baseline đang chạy; PostgreSQL của ứng dụng chưa khởi động. Phần `evaluate.py` hiện tại vẫn là luồng nội bộ trên 180 câu tiếng Việt, không tự chuyển sang EHRSQL khi chạy script baseline.
