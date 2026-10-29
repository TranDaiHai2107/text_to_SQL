# Docker Desktop startup recovery — 28/10/2026

Lỗi hiển thị: Inference Manager không truy cập/xóa được endpoint `Docker/run/dockerInference`. Kiểm tra thực tế thấy file 0 byte, thuộc tính `Archive, ReparsePoint`. Docker Desktop 4.86.0.236216 dừng trước khi Linux engine pipe xuất hiện.

Sau khi vượt endpoint đầu, backend gặp cùng dạng lỗi tại `docker-secrets-engine/engine.sock`; thư mục đó thực tế chỉ có đúng socket này, không có dữ liệu khác. Triệu chứng cùng lớp với [Docker issue #531](https://github.com/docker/desktop-feedback/issues/531). Không kết luận chắc nguyên nhân cấp kernel chỉ từ thông báo lỗi.

Đã kiểm tra đường dẫn tuyệt đối, dừng đúng tiến trình Docker, đổi tên các thư mục socket tạm sang bản giữ lại cùng thư mục cha rồi khởi động lại:

- `C:\Users\ASUS\AppData\Local\Docker\run.stale.20261028_220239`
- `C:\Users\ASUS\AppData\Local\Docker\run.stale.20261028_220557`
- `C:\Users\ASUS\AppData\Local\docker-secrets-engine.stale.20261028_220557`

Không xóa thư mục, không Factory Reset, không Docker prune, không di chuyển VHDX/image/volume. Không thay settings. Những thư mục trên vẫn được giữ để truy vết; không tự dọn chúng.

Engine đã lên lại ở phiên bản 29.7.2; container `text_to_sql-probgate-baseline-1` được khởi động bằng image đã có `3f8695969ab1b9d4521aa9d77545219cd99f4d5331da38d66d2ca5ffc0076792`. Đã dùng lại container để chấm đủ 1.167 câu của năm nhánh. RS trên host và Docker khớp.

Đây là phục hồi thành công phiên khởi động hiện tại, chưa phải chứng minh lỗi Windows/Docker không thể tái diễn. Nếu tái diễn, ưu tiên giữ log và dữ liệu; không lặp reset factory.

DeepSeek inference dùng API và SQLite trên host, nên không bị ngắt bởi sự cố Docker. Không tải diagnostics lên bên thứ ba.
