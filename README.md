# Hướng dẫn chạy và demo TDTU iBanking

## 1. Khởi động ứng dụng

1. Mở Docker Desktop và đợi Docker Engine báo đang chạy.
2. Mở PowerShell, chuyển đến thư mục dự án:

   ```powershell
   cd D:\Visual_Studio_Code\SOA\Midterm-Kien-Truc-HDV
   ```

3. Tạo và khởi động toàn bộ ứng dụng:

   ```powershell
   docker compose up -d --build --wait
   ```

   Lần đầu chạy, Docker tải image, build các service và tạo database; có thể mất vài phút.

4. Kiểm tra trạng thái:

   ```powershell
   docker compose ps
   ```

   Đợi các service ở trạng thái `Up`; database `db` cần `healthy`.

5. Mở <http://localhost:18080>. Trang chính sẽ chuyển đến đăng nhập.

Nếu Docker không kết nối được Engine, mở Docker Desktop và đợi Engine khởi động. Nếu cổng `18080` đang được sử dụng, đóng ứng dụng khác đang chiếm cổng đó rồi chạy lại.

## 2. Tài khoản demo

| Tên đăng nhập | Mật khẩu | MSSV | Email nhận OTP |
|---|---|---|---|
| `phuc123` | `123456` | `524K0011` | `524k0011@student.tdtu.edu.vn` |
| `khiem123` | `123456` | `524K0006` | `524k0006@student.tdtu.edu.vn` |
| `nhi123` | `123456` | `523V0005` | `523v0005@student.tdtu.edu.vn` |

Để demo thanh toán thành công, dùng `phuc123`. Mỗi tài khoản chỉ được thanh toán học phí của MSSV liên kết với email tài khoản đó.

## 3. Demo luồng thanh toán thành công

1. Đăng nhập `phuc123` / `123456`.
2. Tại **Tổng quan**, giới thiệu số dư khả dụng, MSSV `524K0011` và các giao dịch gần đây.
3. Chọn **Đóng học phí**. Trang hiển thị thông tin người nộp, email nhận OTP và khoản học phí của chính MSSV `524K0011`.
4. Kiểm tra số tiền, mở **Xem điều khoản thanh toán**, tích xác nhận đã kiểm tra thông tin rồi chọn **Kiểm tra thông tin**.
5. Ở trang **Kiểm tra giao dịch**, đối chiếu người nộp, email, sinh viên, học kỳ và số tiền. Tích đồng ý điều khoản rồi chọn **Gửi mã OTP**.
6. Mở hộp thư `524k0011@student.tdtu.edu.vn`, tìm thư có tiêu đề **[iBanking TDTU] Mã OTP xác nhận thanh toán học phí**. Nếu chưa thấy, kiểm tra Spam. Không tìm OTP trong Mailpit.
7. Nhập mã OTP 6 chữ số trên trang **Xác thực OTP**, sau đó chọn **Xác minh & thanh toán**. Mã có hiệu lực trong 5 phút.
8. Khi thấy thông báo **Thanh toán thành công**, kiểm tra biên lai gồm mã giao dịch, người nộp, sinh viên, số tiền và số dư mới. Hệ thống cũng gửi email xác nhận thanh toán đến hộp thư sinh viên.
9. Chọn **Xem lịch sử** hoặc **Lịch sử giao dịch** để xác nhận trạng thái giao dịch là **Thành công**.

Với dữ liệu mới khởi tạo, học phí mẫu của `524K0011` là `750.000 VNĐ`. Sau giao dịch thành công, số dư giảm tương ứng và học phí được đánh dấu đã đóng.

## 4. Demo các trường hợp kiểm tra khác

### Không được thanh toán thay sinh viên khác

1. Đăng nhập `khiem123` / `123456`.
2. Thử tra cứu hoặc tạo giao dịch cho MSSV `524K0011` của tài khoản `phuc123`.
3. Ứng dụng chỉ lấy MSSV từ tài khoản đang đăng nhập; không cho sửa MSSV để thanh toán thay người khác.

### Không đủ số dư

1. Đăng nhập `nhi123` / `123456`.
2. Tra cứu học phí của MSSV `523V0005`.
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

Nếu email chưa đến, kiểm tra đúng hộp thư của tài khoản đang đăng nhập và thư mục Spam. SMTP báo gửi thành công không đảm bảo email đã vào Inbox; hệ thống email TDTU có thể lọc hoặc chặn thư từ bên ngoài.

## 7. Dừng hoặc chạy lại từ dữ liệu ban đầu

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
