# Hướng dẫn chạy và demo TDTU iBanking

## 1. Khởi động ứng dụng

1. Mở Docker Desktop và đợi Docker Engine báo đang chạy.
2. Mở PowerShell, chuyển đến thư mục dự án:

   ```powershell
   cd D:\Visual_Studio_Code\SOA\Midterm-Kien-Truc-HDV
   ```

3. Cấu hình SMTP trong file `.env` ở thư mục gốc. Nếu chưa có file, tạo từ mẫu:

   ```powershell
   Copy-Item .env.example .env
   ```

   Mở `.env`, đặt `EMAIL_PROVIDER=smtp`, `SMTP_HOST=smtp.gmail.com`, `SMTP_PORT=587`, `SMTP_USE_TLS=true`; điền `SMTP_USER` bằng Gmail gửi thư và `SMTP_PASSWORD` bằng **Mật khẩu ứng dụng Google** (không phải mật khẩu đăng nhập Gmail). Địa chỉ trong `MAIL_FROM` phải trùng `SMTP_USER`. Không chia sẻ hoặc commit `.env`.

4. Tạo và khởi động toàn bộ ứng dụng:

   ```powershell
   docker compose up -d --build --wait
   ```

   Lần đầu chạy, Docker tải image, build các service và tạo database; có thể mất vài phút.

5. Kiểm tra trạng thái:

   ```powershell
   docker compose ps
   ```

   Đợi các service ở trạng thái `Up`; database `db` cần `healthy`.

6. Mở <http://localhost:18080>. Trang chính sẽ chuyển đến đăng nhập.

Nếu Docker không kết nối được Engine, mở Docker Desktop và đợi Engine khởi động. Nếu cổng `18080` đang được sử dụng, đóng ứng dụng khác đang chiếm cổng đó rồi chạy lại.

## 2. Tài khoản demo

| Tên đăng nhập | Mật khẩu | MSSV | Email nhận OTP |
|---|---|---|---|
| `phuc123` | `123456` | `524K0011` | `524k0011@student.tdtu.edu.vn` |
| `khiem123` | `123456` | `524K0006` | `524k0006@student.tdtu.edu.vn` |
| `tin123` | `123456` | `524K0033` | `524k0033@student.tdtu.edu.vn` |
| `nhu123` | `123456` | `524V0007` | `524v0007@student.tdtu.edu.vn` |
| `nhi123` | `123456` | `523V0005` | `523v0005@student.tdtu.edu.vn` |

Một tài khoản có thể thanh toán học phí cho nhiều sinh viên. MSSV cần đóng được nhập và tra cứu riêng trên trang **Đóng học phí**; email nhận OTP vẫn luôn là email cố định của tài khoản đang đăng nhập.

## 3. Demo luồng thanh toán thành công

1. Đăng nhập `phuc123` / `123456`.
2. Tại **Tổng quan**, giới thiệu số dư khả dụng, MSSV `524K0011` và các giao dịch gần đây.
3. Chọn **Đóng học phí**, nhập MSSV cần đóng rồi chọn **Tra cứu**. Có thể nhập MSSV khác với MSSV liên kết email; email nhận OTP vẫn là email tài khoản `phuc123`.
4. Kiểm tra số tiền, mở **Xem điều khoản thanh toán**, tích xác nhận đã kiểm tra thông tin rồi chọn **Kiểm tra thông tin**.
5. Ở trang **Kiểm tra giao dịch**, đối chiếu người nộp, email, sinh viên, học kỳ và số tiền. Tích đồng ý điều khoản rồi chọn **Gửi mã OTP**.
6. Mở email của tài khoản người nộp `phuc123` (`524k0011@student.tdtu.edu.vn`), tìm thư có tiêu đề **[iBanking TDTU] Mã OTP xác nhận thanh toán học phí**. Nếu chưa thấy, kiểm tra Spam.
7. Nhập mã OTP 6 chữ số trên trang **Xác thực OTP**, sau đó chọn **Xác minh & thanh toán**. Mã có hiệu lực trong 5 phút.
8. Khi thấy thông báo **Thanh toán thành công**, kiểm tra biên lai gồm mã giao dịch, người nộp, sinh viên, số tiền và số dư mới. Hệ thống cũng gửi email xác nhận thanh toán đến email tài khoản người nộp.
9. Chọn **Xem lịch sử** hoặc **Lịch sử giao dịch** để xác nhận trạng thái giao dịch là **Thành công**.

Với dữ liệu mới khởi tạo, học phí mẫu của `524K0011` là `750.000 VNĐ`. Sau giao dịch thành công, số dư giảm tương ứng và học phí được đánh dấu đã đóng.

## 4. Demo các trường hợp kiểm tra khác

### Thanh toán học phí cho sinh viên khác

1. Đăng nhập `khiem123` / `123456`.
2. Tại **Đóng học phí**, nhập MSSV `524K0011` rồi chọn **Tra cứu**.
3. Kiểm tra tên sinh viên và số tiền. OTP sẽ được gửi đến email tài khoản người nộp `524k0006@student.tdtu.edu.vn`, không đổi theo sinh viên được thanh toán.

### Không đủ số dư

1. Đăng nhập `nhi123` / `123456`.
2. Tra cứu học phí MSSV `523V0005` (hoặc khoản học phí lớn hơn số dư).
3. Số dư khả dụng mẫu thấp hơn khoản học phí, nên nút tiếp tục thanh toán không khả dụng.

### OTP sai hoặc hết hạn

- Nhập sai OTP: giao dịch còn cho thử lại nếu chưa đạt giới hạn.
- Nhập sai đủ 3 lần: giao dịch chuyển `FAILED`, không trừ số dư và không đóng học phí.
- Không xác nhận trong 5 phút: OTP hết hạn và giao dịch bị hủy.

## 5. Xem thông tin tài khoản và lịch sử

- Chọn **Tài khoản** để xem họ tên, MSSV, số điện thoại và email đã liên kết; thông tin này chỉ đọc.
- Chọn **Lịch sử giao dịch** để tìm theo mã giao dịch/sinh viên hoặc lọc theo trạng thái và thời gian.
- Chọn một giao dịch trong danh sách để xem chi tiết.

## 6. Xử lý khi app hoặc email có lỗi

Kiểm tra trạng thái container:

```powershell
docker compose ps
```

Xem log gateway và các service xử lý thanh toán/email:

```powershell
docker compose logs --tail 100 gateway payment-service notification-service
```

Nếu vừa thay đổi file cấu hình Compose hoặc cần build lại ứng dụng:

```powershell
docker compose up -d --build --wait
```

Nếu email chưa đến, kiểm tra đúng hộp thư của tài khoản đang đăng nhập và thư mục Spam. Xem log Notification Service để kiểm tra lỗi kết nối/xác thực SMTP:

```powershell
docker compose logs --tail 100 notification-service
```

Sau khi sửa `.env`, tạo lại Notification Service để nhận cấu hình mới:

```powershell
docker compose up -d --build --force-recreate notification-service
```

Gửi SMTP thành công không đảm bảo thư vào Inbox; hệ thống email TDTU có thể lọc hoặc chặn thư từ bên ngoài.

Để kiểm tra riêng SMTP mà không tạo giao dịch hoặc thay đổi số dư/trạng thái học phí, chạy khi các service đang hoạt động:

```powershell
python test_concurrency.py
```

Script đọc toàn bộ tài khoản trong `auth_db`, bỏ qua email không thuộc miền sinh viên TDTU, rồi gửi email OTP kiểm thử đến các địa chỉ hợp lệ. Mã trong email chỉ để kiểm tra nhận thư, không dùng để thanh toán. Kiểm tra Inbox/Spam sau khi chạy.

## 7. Reset thủ công để demo lại hoặc chạy lại từ dữ liệu ban đầu

Có thể reset dữ liệu bằng SQL khi Docker Compose đang chạy, không cần xóa volume hay khởi động lại app.

### Reset toàn bộ demo và xóa lịch sử giao dịch

Các lệnh sau xóa lịch sử giao dịch và OTP, xóa log thao tác số dư, đưa số dư ba tài khoản demo về ban đầu, đồng thời chuyển tất cả khoản học phí về chưa đóng. Chỉ chạy trong môi trường demo local; thao tác xóa lịch sử không thể hoàn tác.

**macOS / Linux** — mở Terminal tại thư mục dự án và chạy từng khối:

```sh
docker compose exec -T db psql -U root -d payment_db <<'SQL'
DELETE FROM "XacThucOTP";
DELETE FROM "GiaoDich";
SQL

docker compose exec -T db psql -U root -d auth_db <<'SQL'
DELETE FROM "BalanceOperation";
UPDATE "NguoiDung"
SET "SoDuKhaDung" = CASE "TenDangNhap"
    WHEN 'khiem123' THEN 5000000.00
    WHEN 'phuc123' THEN 15500000.00
    WHEN 'nhi123' THEN 1000000.00
END
WHERE "TenDangNhap" IN ('khiem123', 'phuc123', 'nhi123');
SQL

docker compose exec -T db psql -U root -d tuition_db <<'SQL'
UPDATE "HocPhi"
SET "TrangThai" = 'CHUA_DONG',
    "MaGiaoDichThanhToan" = NULL;
SQL
```

**Windows Command Prompt (CMD)** — mở CMD tại thư mục dự án và chạy từng dòng:

```cmd
echo DELETE FROM "XacThucOTP"; | docker compose exec -T db psql -U root -d payment_db
echo DELETE FROM "GiaoDich"; | docker compose exec -T db psql -U root -d payment_db
echo DELETE FROM "BalanceOperation"; | docker compose exec -T db psql -U root -d auth_db
echo UPDATE "NguoiDung" SET "SoDuKhaDung" = CASE "TenDangNhap" WHEN 'khiem123' THEN 5000000.00 WHEN 'phuc123' THEN 15500000.00 WHEN 'nhi123' THEN 1000000.00 END WHERE "TenDangNhap" IN ('khiem123', 'phuc123', 'nhi123'); | docker compose exec -T db psql -U root -d auth_db
echo UPDATE "HocPhi" SET "TrangThai" = 'CHUA_DONG', "MaGiaoDichThanhToan" = NULL; | docker compose exec -T db psql -U root -d tuition_db
```

Mỗi lệnh thành công sẽ báo số dòng bị ảnh hưởng. Lịch sử trang **Giao dịch** sẽ trống sau khi reset.

### Reset số dư và học phí nhưng giữ lịch sử (PowerShell)

Nếu chỉ muốn thanh toán lại một khoản, không xóa lịch sử, có thể reset tài khoản `phuc123` và học phí của `524K0011` như sau. Thay thông tin tương ứng nếu demo dữ liệu khác:

```powershell
@'
UPDATE "NguoiDung"
SET "SoDuKhaDung" = 15500000.00
WHERE "TenDangNhap" = 'phuc123';
'@ | docker compose exec -T db psql -U root -d auth_db

@'
UPDATE "HocPhi"
SET "TrangThai" = 'CHUA_DONG',
    "MaGiaoDichThanhToan" = NULL
WHERE "MSSV" = '524K0011'
  AND "HocKy" = 'HK1-2026';
'@ | docker compose exec -T db psql -U root -d tuition_db
```

Cách này giữ nguyên lịch sử giao dịch. Chỉ chạy trong môi trường demo local.

Dừng ứng dụng nhưng giữ dữ liệu:

```powershell
docker compose down
```

Muốn xóa dữ liệu database và khởi tạo lại dữ liệu demo ban đầu:

```powershell
docker compose down --volumes
docker compose up -d --build --wait
```

`--volumes` xóa dữ liệu giao dịch và database hiện tại của project `midterm_soa_demo`.
