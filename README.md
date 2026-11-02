# Hướng dẫn chạy và demo TDTU iBanking

README này chỉ hướng dẫn cài/chạy và demo ứng dụng từng bước. Phần báo cáo, sơ đồ UML/ERD và giải thích kiến trúc được chuẩn bị riêng.

## 1. Chuẩn bị

- Cài và mở Docker Desktop, chờ Docker Engine khởi động.
- Mở PowerShell tại thư mục dự án.
- Gmail cá nhân đã xác thực là địa chỉ gửi; OTP và biên lai gửi tới email sinh viên đang đăng nhập. Trường `From` có thể hiện tên `iBanking TDTU`, nhưng địa chỉ gửi thực vẫn là Gmail.
- Không dùng mật khẩu Gmail thông thường. Nếu tài khoản trường không hỗ trợ SMTP/App Password hoặc không cho phép gửi bằng địa chỉ trường, cần dùng SMTP relay/thông tin do trường cấp.

## 2. Cấu hình email và chạy ứng dụng

Nếu chưa có `.env`, tạo từ file mẫu mà không ghi đè cấu hình local hiện có:

```powershell
if (!(Test-Path .env)) { Copy-Item .env.example .env }
```

Mở `.env` và cấu hình Gmail SMTP theo tài khoản cá nhân của ông:

```env
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USE_TLS=true
SMTP_USER=your-account@gmail.com
SMTP_PASSWORD=your-gmail-app-password
MAIL_FROM=iBanking TDTU <your-account@gmail.com>
```

Tạo App Password cho Gmail sau khi bật xác minh 2 bước; không dùng mật khẩu đăng nhập Gmail thường. `SMTP_USER` phải trùng địa chỉ trong `MAIL_FROM`. Tên hiển thị là `iBanking TDTU`, nhưng người gửi thực là Gmail đó. Người nhận vẫn là email `@student.tdtu.edu.vn` trong hồ sơ tài khoản đang đăng nhập (ví dụ `phuc123` nhận tại `524k0011@student.tdtu.edu.vn`); email ngoài domain sinh viên bị chặn.

Khởi chạy ứng dụng. Luồng chạy chính và stack kiểm thử đều dùng SMTP thật theo cấu hình `.env`:

```powershell
docker compose up -d --build --wait
```

Chờ lệnh hoàn tất, rồi mở:

- Ứng dụng: [http://localhost](http://localhost)
- Hộp thư thật của email tài khoản sinh viên nhận OTP.

Tài khoản demo:

| Tên đăng nhập | Mật khẩu | MSSV |
|---|---|---|
| `phuc123` | `123456` | `524K0011` |
| `khiem123` | `123456` | Theo email tài khoản |
| `nhi123` | `123456` | Theo email tài khoản |

Nếu không mở được trang, kiểm tra trạng thái container:

```powershell
docker compose ps
```

Nếu cổng `80` đã được ứng dụng khác sử dụng, đóng ứng dụng đó rồi chạy lại lệnh khởi động.

## 3. Demo luồng thanh toán thành công

1. Truy cập [http://localhost](http://localhost), đăng nhập bằng `phuc123` / `123456`.
2. Ở trang **Tổng quan**, giới thiệu số dư, MSSV và danh sách giao dịch gần đây.
3. Chọn **Đóng học phí**. Tài khoản `phuc123` chỉ tra cứu và thanh toán khoản học phí của MSSV `524K0011`; MSSV và email tài khoản không thể sửa.
4. Kiểm tra khoản học phí, tích điều khoản rồi chọn tiếp tục.
5. Ở màn hình rà soát, kiểm tra email nhận OTP, sinh viên, học kỳ và số tiền; chọn **Gửi mã OTP**.
6. Mở hộp thư thật của tài khoản sinh viên, tìm email có tiêu đề `[iBanking TDTU] Mã OTP xác nhận thanh toán học phí`. Kiểm tra thư mục Spam nếu chưa thấy thư đến.
7. Kiểm tra địa chỉ thư:
   - **From:** `iBanking TDTU <địa chỉ Gmail đã cấu hình>`
   - **To:** email trong hồ sơ tài khoản đang đăng nhập (với `phuc123`: `524k0011@student.tdtu.edu.vn`).
   - Địa chỉ gửi và nhận trùng nhau trong tài khoản demo.
8. Nhập OTP trong vòng 5 phút và xác nhận thanh toán.
9. Xem biên lai, sau đó mở **Lịch sử giao dịch** để xác nhận giao dịch có trạng thái `SUCCESS`. Hộp thư thật nhận thêm email biên lai.

OTP có hiệu lực 5 phút. Nhập sai đủ 3 lần hoặc để OTP hết hạn sẽ hủy giao dịch (`FAILED`), không trừ số dư và không gạch nợ học phí; giao diện báo kết quả rồi quay về trang tổng quan.

> Nếu gửi không thành công, kiểm tra log bằng `docker compose logs --tail 100 notification-service payment-service`. Gmail SMTP xác nhận gửi thành công không đảm bảo thư vào Inbox TDTU; chính sách của trường có thể chặn thư từ bên ngoài.

## 4. Kiểm tra dữ liệu sau thanh toán

Chạy các lệnh sau trong PowerShell. Mỗi service nghiệp vụ dùng một database riêng trong PostgreSQL container của project demo:

```powershell
docker compose exec -T db psql -U root -d auth_db -c 'SELECT "MaNguoiDung", "TenDangNhap", "SoDuKhaDung" FROM "NguoiDung";'
docker compose exec -T db psql -U root -d tuition_db -c 'SELECT "MaHocPhi", "MSSV", "TrangThai" FROM "HocPhi";'
docker compose exec -T db psql -U root -d payment_db -c 'SELECT "MaGiaoDich", "MSSV", "TrangThai", "SoTienGiaoDich" FROM "GiaoDich" ORDER BY "NgayGiaoDich" DESC LIMIT 10;'
```

Sau thanh toán thành công, số dư giảm theo số tiền học phí, khoản học phí chuyển thành `DA_DONG`, và giao dịch được lưu với trạng thái `SUCCESS`.

## 5. Chạy kiểm thử demo (không bắt buộc)

Mở PowerShell tại thư mục dự án. Các test dùng SMTP đã cấu hình trong `.env` và gửi OTP/biên lai thật; kịch bản cần OTP sẽ yêu cầu nhập mã nhận được. Mỗi lệnh dưới đây tự tạo stack test cô lập, chạy kịch bản rồi dọn stack sau khi hoàn tất:

```powershell
python test_concurrency.py
```

Lệnh trên chạy hai kịch bản:

- `concurrency1`: hai giao dịch cùng tranh thanh toán một khoản học phí; chỉ một giao dịch được thành công.
- `concurrency2`: tài khoản khác bị chặn khi thử thanh toán học phí của `phuc123`.

Có thể chạy riêng:

```powershell
python test_concurrency.py concurrency1
python test_concurrency.py concurrency2
```

Các kịch bản cần OTP sẽ gửi email thật và yêu cầu nhập OTP đọc từ hộp thư. Đảm bảo `.env` có SMTP credentials hợp lệ trước khi chạy. Khởi chạy project test cô lập trước:

```powershell
docker compose -p midterm-check -f docker-compose.yml -f docker-compose.test.yml up -d --build --wait
```

Sau đó, để chạy các kịch bản API, OTP hoặc Gateway trên stack test, thiết lập biến môi trường:

```powershell
$env:DEMO_GATEWAY_URL = "http://localhost:18080/api/v1"
$env:TEST_COMPOSE_PROJECT = "midterm-check"
$env:TEST_COMPOSE_FILES = "docker-compose.yml;docker-compose.test.yml"
```

Chạy một kịch bản mỗi lần:

```powershell
python tests\demo_test.py api
python tests\demo_test.py otp
python tests\demo_test.py gateway
```

Các kịch bản này tạo giao dịch và thay đổi dữ liệu demo. Để đưa dữ liệu về trạng thái ban đầu trước khi chạy kịch bản khác, xóa riêng stack demo rồi khởi động lại:

```powershell
docker compose -p midterm-check -f docker-compose.yml -f docker-compose.test.yml down --remove-orphans --volumes
docker compose -p midterm-check -f docker-compose.yml -f docker-compose.test.yml up -d --build --wait
```

Sau khi chạy test, dừng riêng stack test:

```powershell
docker compose -p midterm-check -f docker-compose.yml -f docker-compose.test.yml down --remove-orphans --volumes
```

## 6. Dừng ứng dụng demo

Sau khi trình bày xong, dừng và xóa riêng stack demo:

```powershell
docker compose down
```

Thêm `--volumes` nếu muốn xóa cả dữ liệu PostgreSQL demo.
