# ProbGate / EHRSQL 2024 — bản tái hiện tách biệt

Thư mục này dành riêng cho bài **ProbGate at EHRSQL 2024**, không tích hợp RAG, Validator hoặc Self-Correction của dự án hiện tại. Chuẩn bị ngày 19/10/2026.

**Phạm vi đã chuẩn bị:** toàn bộ 11 dòng baseline/ablation của Table 1 và Table 2, mã gốc tác giả, database tác giả, dataset cùng phiên bản, cấu hình postprocessing, bộ chấm và hướng dẫn cho bước chạy sau.

Trạng thái chuẩn bị ngày 19/10/2026 được giữ tại `PREPARATION_STATUS.json`. Đợt rà soát/chấm cache ngày 23/10/2026 được ghi riêng trong `FINAL_RUN_REVIEW.md` và thư mục `runs/audit_20261023_docker`. Điểm trong cấu hình vẫn là điểm công bố; điểm thực chạy luôn nằm trong `scores*.json`. Việc giữ đủ nguồn không có nghĩa mọi checkpoint của tác giả đã được công khai. Xem `UPSTREAM_NOTES.md` để biết chính xác các thiếu hụt.

## Nguồn

- [Bài báo, ClinicalNLP 2024](https://aclanthology.org/2024.clinicalnlp-1.65/).
- [PDF](https://aclanthology.org/2024.clinicalnlp-1.65.pdf).
- [Mã nguồn tác giả](https://github.com/venzino-han/probgate_ehrsql).
- Metadata, citation và danh sách thí nghiệm: `PAPER.md`.
- Model gốc và nơi xuất hiện trong source: `MODELS.md`.
- Kết luận dataset hiện tại có dùng để so trực tiếp được không: `DATASET_REVIEW.md`; số liệu kiểm tra: `DATASET_AUDIT.json`.
- Toàn bộ điểm RS công bố của 11 cấu hình đã ghi trong `PAPER.md`, tách rõ dev và test.
- Container riêng và lệnh chạy replay: `DOCKER.md`; script chạy chủ động `run_cached_baselines.ps1`.

## Cấu trúc

```text
probgate_ehrsql_2024/
  README.md
  PAPER.md
  MODELS.md
  UPSTREAM_NOTES.md
  source_manifest.json          # commit và SHA256 của từng file
  configs/
    experiments.json           # 7 dev + 4 test, điểm công bố và artifact cần có
    reserved_words.json        # trích nguyên từ notebook tác giả
  upstream/                    # 52 file tracked, byte-for-byte từ git commit
    README.md
    schema.txt
    schema_tokens.txt
    src/
      *.py, *.ipynb
      requirements.txt          # nguyên môi trường tác giả
      data/mimic_iv/            # database, schema, questions tác giả
      log_probability_final_test.json
      log_probability_test_new.pickle
  data/
    inputs/{train,dev,test}.json # câu hỏi, không chứa gold
    gold/{train,dev,test}/       # chỉ dùng huấn luyện/chấm đúng phạm vi
  baseline_core.py              # adapter offline, không có model client
  reproduce.py                  # list / plan / verify / postprocess / score
  tools/prepare_snapshot.py     # chuẩn bị từ các repo đã tải trong research/
  tests/test_baseline_core.py   # test trên dữ liệu giả rất nhỏ
```

`upstream/` và `data/` đã được materialize trong workspace này. Chúng được ignore trong Git vì chứa database và cache lớn. `source_manifest.json` lưu checksum để kiểm tra. Folder chạy `reproduce.py` không phụ thuộc các module ứng dụng hoặc `research/`; chỉ script chuẩn bị snapshot mới cần các repo nguồn đã tải.

## Phiên bản được giữ

Source ProbGate: `2dcc2230ea049e7fb87160df922933b4ae2645b9`.

Đầu vào giữ đúng `mimic_iv_demo_1.0_{train,valid,test}` tác giả đã dùng: 5.124 train, 1.163 dev, 1.167 test. Gold dev/test bổ sung từ commit EHRSQL ghi trong manifest; đã đối chiếu đúng từng ID/câu hỏi với source tác giả. Database là đúng file đi kèm repo ProbGate, không thay bằng database Mini hoặc bản M3 khác.

Không dùng EHRSQL v1.0.5/v1.1.2 đã khảo sát cho M3 để âm thầm thay dữ liệu của ProbGate.

## Các thao tác chỉ kiểm tra chuẩn bị

Từ thư mục này, dùng Python 3.9+:

```powershell
python reproduce.py verify
python reproduce.py list
python reproduce.py plan
python reproduce.py plan --experiment test_gpt_probgate_425_gef
python -m unittest discover -s tests -v
```

Các lệnh trên không import SDK LLM, tải model, thực thi SQL benchmark hoặc đọc API key. Bộ test tạo một SQLite giả tạm thời để kiểm tra logic read-only/GEF; không chạy trên EHRSQL.

## Chạy lại

### Nhánh test có cache gốc

Bốn cấu hình test dùng chung file JSON SQL/logprobs công khai, nên có thể replay phần hậu xử lý mà không cần inference mới. Không tải pickle bằng `pickle.load`; adapter chỉ dùng bản JSON.

Ví dụ cấu hình cuối, khi chuyển sang giai đoạn chạy:

```powershell
python reproduce.py postprocess --experiment test_gpt_probgate_425_gef --raw upstream/src/log_probability_final_test.json --output runs/test_gpt_probgate_425_gef/prediction.json
python reproduce.py score --split test --scorer official --predictions runs/test_gpt_probgate_425_gef/prediction.json --output runs/test_gpt_probgate_425_gef/scores.json
```

Các ID test còn lại: `test_gpt_ft`, `test_gpt_probgate_450`, `test_gpt_probgate_450_gef`. Thay ID và output path tương ứng. Adapter không ghi đè output có sẵn. Replay cache tái hiện hậu xử lý trên đầu ra tác giả; không được mô tả là đã train lại model.

### Nhánh dev và huấn luyện lại

Xem `python reproduce.py plan` để lấy model, source và artifact cần có cho từng dòng. Mã huấn luyện/inference gốc nằm trong `upstream/`, nhưng chưa có checkpoint riêng của tác giả cho mọi model và có lỗi/chỗ hard-code được liệt kê ở `UPSTREAM_NOTES.md`. Không chạy notebook hàng loạt như một script tự động.

Khi đã có đầu ra model đúng split:

- GPT raw JSON: `{id: [sql, token_logprobs]}`, như cache tác giả; mỗi token chứa `token`, `logprob`.
- T5 evaluation JSON: `[{id, pred, entropy: [token_entropy, ...]}]`.
- Classifier JSON: `{id: "answerable" hoặc "null"}`. Không suy đoán 0/1 thuộc lớp nào.
- Lọc entropy cần `--entropy-threshold` đã được hiệu chuẩn. Adapter từ chối đoán threshold hoặc lấy gold test để tự chọn.
- Nhánh classifier cần `--classifier <file>`; cache test GPT không thay được đầu ra dev/T5/classifier.

Sau đó dùng `postprocess --experiment <id> ...` và `score --split dev ...`.

## Quy tắc được bảo toàn

- ProbGate bỏ token SQL reserved rồi lấy trung bình tối đa 10 logprob thấp nhất.
- `t=387/425/450` trong các dòng thực nghiệm là vị trí rank threshold. Notebook dùng zero-based index và phép `<=`, nên khi đồng hạng số câu từ chối có thể vượt index+1.
- Filtering T5 dùng maximum entropy và `>` so với threshold; không đồng nhất với ProbGate.
- GEF bảo toàn cả việc lọc lỗi và empty results trong code công bố. Khác biệt với mô tả ngắn trong paper được ghi rõ.
- Scoring mặc định `--scorer official`: dùng stored gold, chuẩn hóa giá trị số 3 chữ số và lấy tối đa 100 hàng như EHRSQL. `--scorer author` giữ helper raw trong repo ProbGate để đối soát. Rà soát ngày 23/10 tìm được hai câu mà helper raw phân biệt số với chuỗi số, làm RS0 nhánh GPT FT lệch 0.17 điểm; scorer official cho RS0 73.52 như paper. Hai cách chuẩn hóa không được trộn thành một kết quả. RS0/RS5/RS10/RSN dùng penalty 0/5/10/N. Tất cả ID bắt buộc hiện diện; lỗi query không bị loại khỏi mẫu số. Một số số công bố có chênh lệch dưới 0.01 điểm so với tính trực tiếp; báo cáo giữ nguyên cả số chính xác lẫn target.
- Adapter dùng SQLite read-only và timeout mặc định 30 giây/query. Timeout là ràng buộc vận hành bổ sung, phải ghi lại nếu phát sinh; không có trong pipeline gốc.

## Môi trường

Mã chuẩn bị, adapter và test mới dùng Python standard library. Không cài thêm package ở bước này. Requirements nguyên tác giả được giữ tại `upstream/src/requirements.txt`; không áp dụng nó lên `.venv` của ứng dụng.

Source tác giả thử trên Python 3.9.18. Requirements gốc thiếu một số dependency mà source import và chứa package đặc thù môi trường; việc khóa môi trường training sẽ được giải quyết trước khi chạy model. Không nâng model/SDK hoặc sửa thuật toán ngầm trong gói này.
