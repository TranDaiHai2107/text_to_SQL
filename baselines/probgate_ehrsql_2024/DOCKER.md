# Container baseline SQLite

Service: `probgate-baseline`, profile `baseline`, image `text-to-sql-probgate:local` trong `docker-compose.yml` ở root dự án.

Đã build và kiểm tra ngày **19/10/2026**: container `text_to_sql-probgate-baseline-1` đạt **healthy**, Python 3.12.15 / SQLite 3.40.1. Checksum nguồn/dataset hợp lệ; SQLite có 17 bảng, 94 bệnh nhân; ghi được vào thư mục kết quả. Chưa chạy model, SQL benchmark hoặc tạo điểm số. Chi tiết kiểm tra và image ID: [DOCKER_STATUS.json](DOCKER_STATUS.json).

Container chỉ phục vụ **replay cache và chấm baseline offline**, chưa phải môi trường GPU/training cho các model T5 hoặc môi trường gọi API. Không cài model, không lấy API key của ứng dụng và không chạy experiment khi khởi động.

Cập nhật **23/10/2026**: đã kiểm chứng đủ bốn nhánh test; cấu hình cuối cho RS0=81.92, RS10=74.21 bằng scorer official. Container đã build lại code mới và healthy. Xem [FINAL_RUN_REVIEW.md](FINAL_RUN_REVIEW.md) để phân biệt điểm replay, điểm paper và phần còn thiếu của ứng dụng.

## Database và kết quả

- Database vẫn là file SQLite gốc tác giả, mount qua `/app/upstream` ở chế độ read-only.
- Input/gold mount `/app/data`, read-only.
- Kết quả lưu `/app/runs`, tương ứng `baselines/probgate_ehrsql_2024/runs` trên Windows; xóa container không làm mất thư mục này.
- Code ứng dụng và volume PostgreSQL không mount vào service này.
- Không mở port. SQLite được Python trong container truy cập trực tiếp.
- Container chạy user không phải root, root filesystem read-only, không có network, dùng tối đa 2 CPU / 2 GB RAM.

## Build hoặc khởi động

Chạy từ `D:\Github\text_to_SQL`, sau khi Docker Desktop đã sẵn sàng:

```powershell
docker compose --profile baseline build probgate-baseline
docker compose --profile baseline up -d --wait probgate-baseline
docker compose ps probgate-baseline
```

Startup chỉ kiểm tra checksum, đủ ID/split, SQLite header và metadata 17 bảng. Container sau đó đứng chờ lệnh; không tự chạy GEF, inference hoặc scoring. Các thao tác SELECT metadata/counts không phải đánh giá benchmark.

Kiểm tra thủ công:

```powershell
docker compose exec -T probgate-baseline python docker_runner.py check
docker compose exec -T probgate-baseline python reproduce.py list
docker compose exec -T probgate-baseline python reproduce.py plan --experiment test_gpt_probgate_425_gef
```

Python/SQLite version thực tế được ghi trong log startup. Base image Python 3.12 slim Bookworm đã pin digest trong Dockerfile; image ID/runtime đã build được ghi trong `DOCKER_STATUS.json`. Mỗi run còn có provenance riêng để nhận ra code/image cũ.

## Chạy lại baseline cache

Chạy đủ 4 nhánh test có cache bằng một lệnh, từ root dự án:

```powershell
.\baselines\probgate_ehrsql_2024\run_cached_baselines.ps1
```

Mặc định script dùng scorer `official`, tạo một thư mục run mới theo timestamp. Script tự build lại code, đợi container healthy, kiểm tra hash và chạy đủ SQL gold trước khi replay 4 nhánh. Nó replay output gốc tác giả; không gọi model, không fine-tune. Thời gian phụ thuộc các SQL trong benchmark. Dừng nếu một bước lỗi; không ghi đè output cũ.

Mỗi run có `preflight.json`, bốn thư mục chứa `prediction.json`, `prediction.metadata.json`, `scores.json`, và `comparison.json` tổng hợp điểm thực chạy/điểm paper/chênh lệch. Các file ghi Python/SQLite, hash code, hash đầu vào và timeout. Chênh lệch điểm không được tự sửa thành điểm paper.

Đặt tên lần chạy và timeout rõ ràng:

```powershell
.\baselines\probgate_ehrsql_2024\run_cached_baselines.ps1 -RunName final_official_01 -Scorer official -SqlTimeout 30
```

Muốn đối soát bằng helper raw của tác giả:

```powershell
.\baselines\probgate_ehrsql_2024\run_cached_baselines.ps1 -Scorer author
```

Hai chế độ scorer có normalization khác nhau, phải giữ tên chế độ khi báo cáo. Đợt audit ngày 23/10 cho toàn bộ điểm official chênh dưới 0.01 điểm so với số paper; helper raw lệch hai câu ở nhánh GPT FT. Không dùng hai chế độ như cùng một protocol.

Hoặc chỉ chạy một cấu hình:

```powershell
docker compose exec -T probgate-baseline python reproduce.py postprocess --experiment test_gpt_probgate_425_gef --raw upstream/src/log_probability_final_test.json --output runs/first_trial/prediction.json
docker compose exec -T probgate-baseline python reproduce.py score --split test --scorer official --predictions runs/first_trial/prediction.json --output runs/first_trial/scores.json
```

Chọn tên thư mục khác nếu `first_trial` đã tồn tại.

## Clock và tính tương đương

Mốc thời gian benchmark `2100-12-31 23:59:00` được xử lý bởi `post_process_sql` gốc, không cần đổi đồng hồ Windows/Docker. Scorer không đổi database hoặc schema. Docker không tự bảo đảm điểm khớp: cùng file/annotation/scorer và không bị timeout vẫn là điều kiện cần kiểm tra khi replay.

## Dừng

```powershell
docker compose stop probgate-baseline
```

Các lệnh trên chỉ nhắm service baseline. Không cần dùng `docker compose down` hoặc xóa volume PostgreSQL.

Nếu Docker báo không tìm thấy `dockerDesktopLinuxEngine`, mở/khởi động Docker Desktop và đợi engine Linux sẵn sàng rồi chạy lại build/up. Không cần dựng lại SQLite.
