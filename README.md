# Phân hệ Đóng học phí - iBanking TDTU

Dự án giữa kỳ môn **Kiến trúc hướng dịch vụ (CS504070)**. Ứng dụng mô phỏng phân hệ thanh toán học phí của iBanking: người dùng đăng nhập, tra cứu học phí theo MSSV, xác thực giao dịch bằng OTP gửi qua email và thanh toán bằng số dư tài khoản. Hệ thống được xây dựng theo **kiến trúc Microservices**.

## Mục lục
1. [Kiến trúc hệ thống](#1-kiến-trúc-hệ-thống)
2. [Cài đặt và khởi chạy](#2-cài-đặt-và-khởi-chạy)
3. [Tài khoản và dữ liệu mẫu](#3-tài-khoản-và-dữ-liệu-mẫu)
4. [Hướng dẫn sử dụng](#4-hướng-dẫn-sử-dụng)
5. [REST API](#5-rest-api)
6. [Transaction và Concurrency](#6-transaction-và-concurrency)
7. [Kiểm thử và demo](#7-kiểm-thử-và-demo)
8. [Cấu hình gửi email qua Gmail](#8-cấu-hình-gửi-email-qua-gmail)
9. [Cấu trúc thư mục](#9-cấu-trúc-thư-mục)

---

## 1. Kiến trúc hệ thống

```
                              Trình duyệt
                                   │  http://localhost  (trang web + /api/v1/..., kèm JWT)
                    ┌──────────────▼──────────────────────────┐
                    │  API Gateway (Nginx) :80                │
                    │  - phục vụ giao diện web (frontend/)    │
                    │  - định tuyến /api/v1/... tới service   │
                    │  - chặn API nội bộ, sinh X-Request-ID   │
                    └──────┬──────────────┬──────────────┬────┘
               /auth, /users/me    /tuitions/{mssv}   /payments
          ┌────────────────┘              │              └──────────────┐
          ▼                               ▼                             ▼
┌───────────────────┐      ┌───────────────────┐      ┌───────────────────────┐
│ Auth Service      │      │ Tuition Service   │      │ Payment Service       │
│ :8001             │      │ :8002             │      │ :8003                 │
│ Đăng nhập, JWT,   │◄─────┤ Sinh viên,        │◄─────┤ Giao dịch, OTP,       │
│ thông tin user,   │ REST │ học phí, gạch nợ  │ REST │ điều phối thanh toán  │
│ số dư             │ nội bộ (X-Internal-Key)  │      │ (Saga), lịch sử       │
└────────┬──────────┘      └────────┬──────────┘      └──────┬──────────┬─────┘
         │                          │                        │          │ REST nội bộ
         ▼                          ▼                        ▼          ▼
    ┌─────────┐              ┌────────────┐          ┌────────────┐  ┌──────────────────────┐
    │ auth_db │              │ tuition_db │          │ payment_db │  │ Notification Service │
    └─────────┘              └────────────┘          └────────────┘  │ :8004  (Adapter)     │
                (PostgreSQL 15, mỗi service một database)            └──────────┬───────────┘
                                                                                │ SMTP
   Chỉ Gateway (:80) và Mailpit (:8025) mở port ra máy host;         ┌──────────▼───────────┐
   các service và database chỉ giao tiếp trong mạng Docker.         │ Mailpit / Gmail      │
                                                                     └──────────────────────┘
```

| Service | Port (trong mạng Docker) | Database | Trách nhiệm |
|---|---|---|---|
| **Auth Service** | 8001 | `auth_db` (`NguoiDung`) | Đăng nhập, cấp JWT, thông tin người dùng, quản lý số dư (trừ tiền, hoàn tiền) |
| **Tuition Service** | 8002 | `tuition_db` (`SinhVien`, `HocPhi`) | Tra cứu học phí theo MSSV, gạch nợ học phí |
| **Payment Service** | 8003 | `payment_db` (`GiaoDich`, `XacThucOTP`) | Khởi tạo giao dịch, sinh và xác thực OTP, điều phối thanh toán, lịch sử giao dịch |
| **Notification Service** | 8004 | (không cần) | Lớp Adapter gửi thông báo: dựng nội dung email theo mẫu (OTP, thanh toán thành công) và gửi qua kênh được cấu hình (Mailpit/Gmail) |
| **API Gateway** (Nginx) | 80, mở ra host | | Cổng vào duy nhất: phục vụ giao diện web, định tuyến `/api/v1/...` tới service, chặn API nội bộ, sinh `X-Request-ID` |
| Mailpit | 8025, mở ra host | | Hộp thư giả để xem email OTP và email xác nhận khi chạy local |

**Lý do lựa chọn kiến trúc:**
- **Database-per-service:** mỗi service chỉ đọc/ghi database của chính mình. Service khác muốn dùng dữ liệu phải gọi qua REST API, ví dụ Payment Service không trừ tiền trực tiếp trong bảng `NguoiDung` mà gọi `POST /users/{id}/deduct-balance` của Auth Service. Nhờ vậy ranh giới dữ liệu rõ ràng, mỗi service có thể thay đổi schema hoặc triển khai độc lập.
- **Giao tiếp REST đồng bộ:** luồng thanh toán cần biết kết quả ngay (đủ số dư hay không, học phí đã bị người khác thanh toán hay chưa) để trả về cho người dùng, nên dùng REST đồng bộ thay vì message broker.
- **Payment Service điều phối (orchestration):** Payment gọi lần lượt Auth (trừ tiền) và Tuition (gạch nợ). Nếu gạch nợ thất bại sau khi đã trừ tiền, Payment gọi API hoàn tiền của Auth (giao dịch bù trừ theo mô hình Saga).
- **Adapter cho dịch vụ bên ngoài (Notification Service):** Payment Service không gọi SMTP trực tiếp mà gọi REST `POST /notifications` với tên mẫu và dữ liệu. Bên trong Notification Service, mỗi kênh gửi là một class cài đặt chung interface `NotificationSender` (`senders.py`). Đổi Mailpit sang Gmail chỉ cần đổi `.env`; thêm kênh mới (Zalo, SMS) chỉ cần viết thêm một adapter, không sửa Payment Service.
- **Idempotency Key:** mọi lời gọi có thể bị gửi lại đều mang một khoá để bên nhận không xử lý hai lần: frontend gửi header `Idempotency-Key` khi tạo giao dịch; Payment dùng mã giao dịch làm khoá khi gọi Auth (trừ/hoàn tiền) và Tuition (gạch nợ).
- **API Gateway:** trình duyệt chỉ biết một địa chỉ `http://localhost`. Nginx định tuyến theo đường dẫn (`/api/v1/auth`, `/users/me` → Auth; `/tuitions` → Tuition; `/payments` → Payment), nên frontend không cần biết service nào chạy ở đâu, không cần CORS, và có thể thay đổi/tách service phía sau mà không sửa frontend. Gateway chỉ mở các API công khai; API nội bộ trả 404 nếu gọi từ ngoài. Các service và database không mở port ra máy host.
- **Logging & tracing:** mỗi request có một `X-Request-ID` do Gateway sinh ra (hoặc giữ nguyên nếu client đã gửi). Mọi service dùng module chung `backend/shared/observability.py`: ghi ID này vào mọi dòng log và gửi tiếp khi gọi service khác (kể cả tác vụ nền như gửi email xác nhận, worker phục hồi giao dịch). Lọc log theo một ID là thấy toàn bộ đường đi của một giao dịch qua các service (xem mục 7).
- **Bảo mật:** frontend gọi API bằng **JWT** do Auth Service cấp, các service tự xác thực token bằng khóa ký dùng chung. API nội bộ (trừ tiền, hoàn tiền, gạch nợ, gửi thông báo) được bảo vệ 2 lớp: Gateway không định tuyến tới, và service yêu cầu header `X-Internal-Key`.

**Công nghệ:** Python 3.10, FastAPI, SQLAlchemy, PostgreSQL 15, PyJWT, HTML/CSS/JavaScript thuần, Nginx, Docker Compose, Mailpit.

## 2. Cài đặt và khởi chạy

**Yêu cầu:** Docker Desktop đang chạy. Cần port 80 (Gateway) và 8025 (Mailpit) còn trống.

Không cần cấu hình gì thêm: mặc định email được gửi vào Mailpit. Muốn gửi email thật qua Gmail, xem [mục 8](#8-cấu-hình-gửi-email-qua-gmail).

```bash
docker compose up -d --build
```

Lần đầu chạy, Docker build image và chạy `init.sql` để tạo 3 database cùng dữ liệu mẫu. Đợi các container khởi động xong bằng `docker compose ps`:

```bash
docker compose ps
```

Nếu service chưa sẵn sàng, xem log bằng `docker compose logs -f`.

| Địa chỉ | Nội dung |
|---|---|
| http://localhost | Giao diện web (trang đăng nhập) |
| http://localhost:8025 | Hộp thư Mailpit: xem email OTP và email xác nhận |
| http://localhost/api/v1/auth/docs | Swagger UI của Auth Service (qua Gateway) |
| http://localhost/api/v1/tuitions/docs | Swagger UI của Tuition Service (qua Gateway) |
| http://localhost/api/v1/payments/docs | Swagger UI của Payment Service (qua Gateway) |

Cần gọi thẳng từng service hoặc database để debug (port 8001–8004, 5432, Swagger của Notification ở http://localhost:8004/docs):

```bash
docker compose -f docker-compose.yml -f docker-compose.dev.yml up -d
```

**Reset toàn bộ dữ liệu về ban đầu** (lệnh này xóa volume database hiện tại và chạy lại `init.sql`):

```bash
docker compose down -v
docker compose up -d
```

**Dừng hệ thống:** `docker compose down`

## 3. Tài khoản và dữ liệu mẫu

Mật khẩu của tất cả tài khoản: `123456`

| Tên đăng nhập | Họ tên | Email | Số dư |
|---|---|---|---|
| `khiem123` | Thân Vũ Gia Khiêm | 524k0006@student.tdtu.edu.vn | 5.000.000 |
| `phuc123` | Nguyễn Gia Phúc | 524k0011@student.tdtu.edu.vn | 15.500.000 |
| `nhi123` | Hồng Bảo Nhi | 523v0005@student.tdtu.edu.vn | 1.000.000 |

| MSSV | Sinh viên | Học phí | Trạng thái |
|---|---|---|---|
| `524K0006` | Thân Vũ Gia Khiêm | 8.500.000 | Đã đóng |
| `524K0011` | Nguyễn Gia Phúc | 750.000 | Chưa đóng |
| `523V0005` | Hồng Bảo Nhi | 15.000.000 | Chưa đóng |

Tài khoản người dùng và sinh viên là hai đối tượng độc lập: một người dùng có thể thanh toán học phí cho bất kỳ sinh viên nào.

## 4. Hướng dẫn sử dụng

1. Mở http://localhost, đăng nhập bằng một tài khoản ở bảng trên.
2. Màn hình **Thanh toán học phí** gồm 3 phần:
   - **Người nộp tiền:** họ tên, SĐT, email lấy từ tài khoản đăng nhập, không chỉnh sửa được.
   - **Thông tin học phí:** nhập MSSV, hệ thống tự tra cứu và hiển thị tên sinh viên, số tiền.
   - **Thông tin thanh toán:** số dư khả dụng, số tiền cần thanh toán, điều khoản.
3. Nút **Xác nhận giao dịch** chỉ bật khi khoản học phí tồn tại và chưa đóng, số dư đủ và đã đồng ý điều khoản.
4. Bấm xác nhận, hệ thống gửi **mã OTP** qua email. Mở http://localhost:8025 để xem mã. OTP có hiệu lực 5 phút, chỉ dùng được 1 lần, nhập sai tối đa 5 lần.
5. Nhập OTP, hệ thống trừ tiền, gạch nợ, lưu lịch sử, gửi email xác nhận và hiển thị kết quả.
6. Trang **Lịch sử** hiển thị các giao dịch đã thực hiện và số dư hiện tại.

## 5. REST API

Base URL: `http://localhost/api/v1` (mọi API công khai đi qua API Gateway). Tất cả API trả về JSON. Lỗi có dạng `{"detail": "<thông báo>"}`. Mọi response có header `X-Request-ID` để tra log.

### API cho frontend

| Method | URI | Xác thực | Mô tả | Status code |
|---|---|---|---|---|
| POST | `/api/v1/auth/login` | | Đăng nhập, trả về JWT | 200, 400, 401 |
| GET | `/api/v1/users/me` | JWT | Thông tin tài khoản đang đăng nhập | 200, 401 |
| GET | `/api/v1/tuitions/{mssv}` | JWT | Tra cứu khoản học phí chưa đóng theo MSSV | 200, 401, 404 |
| POST | `/api/v1/payments` | JWT | Khởi tạo giao dịch và gửi OTP qua email. Header tuỳ chọn `Idempotency-Key`: gửi lại cùng khoá nhận về giao dịch cũ (kèm header `Idempotent-Replayed: true`) | 201, 400, 401, 404, 409, 502 |
| POST | `/api/v1/payments/{transaction_id}/confirm` | JWT | Xác nhận OTP và thực hiện thanh toán | 200, 400, 401, 403, 404, 409 |
| GET | `/api/v1/payments` | JWT | Lịch sử giao dịch của người dùng | 200, 401 |
| GET | `/api/v1/payments/{transaction_id}` | JWT | Chi tiết giao dịch (kèm thời điểm hết hạn OTP) | 200, 401, 403, 404 |

### API nội bộ giữa các service (header `X-Internal-Key`)

Chỉ gọi được trong mạng Docker; gọi qua Gateway nhận 404.

| Method | URI | Service | Mô tả | Status code |
|---|---|---|---|---|
| GET | `/api/v1/users/{id}` | Auth | Thông tin người dùng theo ID | 200, 403, 404 |
| POST | `/api/v1/users/{id}/deduct-balance` | Auth | Trừ số dư (khóa dòng) | 200, 400, 403, 404 |
| POST | `/api/v1/users/{id}/refund` | Auth | Hoàn tiền (giao dịch bù trừ) | 200, 403, 404 |
| GET | `/api/v1/tuitions/detail/{id}` | Tuition | Chi tiết khoản học phí theo ID | 200, 403, 404 |
| POST | `/api/v1/tuitions/{id}/pay` | Tuition | Gạch nợ học phí | 200, 403, 404, 409 |
| POST | `/api/v1/notifications` | Notification | Gửi thông báo theo mẫu (`OTP`, `PAYMENT_SUCCESS`) qua kênh `email` | 201, 400, 403, 502 |

Các API trừ tiền, hoàn tiền, gạch nợ nhận `transaction_id` trong body làm idempotency key: gọi lại cùng mã trả về kết quả cũ, không trừ/hoàn/gạch nợ lần hai.

### Ý nghĩa status code

| Code | Khi nào |
|---|---|
| 200 / 201 | Thành công / tạo giao dịch thành công |
| 400 | Dữ liệu không hợp lệ, số dư không đủ, OTP sai hoặc hết hạn |
| 401 | Chưa đăng nhập, sai mật khẩu, token hết hạn hoặc không hợp lệ |
| 403 | Truy cập giao dịch của người khác, gọi API nội bộ không có khóa |
| 404 | Không tìm thấy sinh viên, học phí hoặc giao dịch; gọi API nội bộ qua Gateway |
| 409 | Học phí đã được thanh toán, giao dịch đã được xử lý, `Idempotency-Key` đã dùng cho yêu cầu khác |
| 502 / 503 | Không gửi được email / service khác không phản hồi |

### Ví dụ

```http
POST /api/v1/payments
Authorization: Bearer <access_token>
Idempotency-Key: 9f1c2a7be4d04c1f8a3e6b5d2c1f0a9e
Content-Type: application/json

{ "MaHocPhi": 2 }
```
```json
201 Created
{
  "transaction_id": "TXN_6113f67879144fb1bc45b74378157995",
  "message": "OTP đã được gửi đến email của bạn.",
  "otp_expires_at": "2026-10-30T07:05:00Z"
}
```

```http
POST /api/v1/payments/TXN_6113f67879144fb1bc45b74378157995/confirm
Authorization: Bearer <access_token>
Content-Type: application/json

{ "otp": "025195" }
```
```json
200 OK
{
  "message": "Thanh toán học phí thành công",
  "transaction_id": "TXN_6113f67879144fb1bc45b74378157995",
  "status": "SUCCESS",
  "new_balance": 14750000.0
}
```

Model request/response đầy đủ của từng API xem tại Swagger UI qua Gateway (`/api/v1/auth/docs`, `/api/v1/tuitions/docs`, `/api/v1/payments/docs`). Nút **Authorize** nhận JWT để thử các API cần đăng nhập.

## 6. Transaction và Concurrency

**Luồng xác nhận thanh toán** (`POST /payments/{id}/confirm`):

```
1. Payment: SELECT ... FOR UPDATE giao dịch -> kiểm tra PENDING, kiểm tra OTP
            -> đánh dấu OTP đã dùng, giao dịch = PROCESSING, COMMIT
2. Payment -> Auth:    POST /users/{id}/deduct-balance   (trừ tiền)
                       thất bại -> giao dịch = FAILED
3. Payment -> Tuition: POST /tuitions/{id}/pay            (gạch nợ)
                       thất bại -> Auth /refund (hoàn tiền) -> giao dịch = FAILED
4. Payment: giao dịch = SUCCESS
5. Payment -> Notification: POST /notifications (email xác nhận, chạy nền)
```

**Tình huống 1: nhiều giao dịch đồng thời trên cùng một tài khoản.** Auth Service trừ tiền trong một database transaction có **khóa dòng** (`SELECT ... FOR UPDATE`) trên bản ghi người dùng. Các request trừ tiền đồng thời phải xếp hàng: request sau chỉ đọc được số dư sau khi request trước đã commit, rồi mới kiểm tra lại `SoDu >= SoTien`. Do đó số dư không bao giờ bị chi vượt. Ngoài ra cột số dư có ràng buộc `CHECK ("SoDuKhaDung" >= 0)`.

**Tình huống 2: nhiều tài khoản cùng thanh toán một khoản học phí.** Tuition Service gạch nợ bằng một câu lệnh UPDATE có điều kiện:
```sql
UPDATE "HocPhi" SET "TrangThai" = 'DA_DONG'
WHERE "MaHocPhi" = :id AND "TrangThai" = 'CHUA_DONG'
```
PostgreSQL khóa dòng khi UPDATE. Request thứ hai phải chờ request đầu commit, sau đó điều kiện `TrangThai = 'CHUA_DONG'` không còn đúng nên 0 dòng được cập nhật và API trả 409. Payment Service nhận 409 thì hoàn tiền cho người đến sau, nên khoản học phí chỉ được thanh toán thành công **một lần** và không ai bị mất tiền.

**Chống xác nhận trùng một giao dịch:** giao dịch bị khóa (`FOR UPDATE`) khi xác nhận và chuyển ngay sang `PROCESSING`. Request thứ hai (bấm nút 2 lần, dùng lại OTP) nhận 409.

**Phục hồi giao dịch dở dang:** Auth ghi sổ `DEBIT`/`REFUND` theo mã giao dịch trong cùng transaction với cập nhật số dư; gọi lại cùng mã không trừ/hoàn tiền lần hai. Tuition lưu mã giao dịch đã gạch nợ; gọi lại cùng mã là idempotent. Payment giữ giao dịch ở `PROCESSING` khi service không phản hồi, rồi worker tự thử lại sau khi service lên lại. Các cột/bảng phục hồi được tạo bằng migration cộng thêm khi service khởi động.

**Chống tạo giao dịch trùng (Idempotency-Key):** frontend sinh một khoá ngẫu nhiên cho mỗi lần bấm "Xác nhận giao dịch" và gửi trong header `Idempotency-Key`. Bảng `GiaoDich` có ràng buộc `UNIQUE (MaNguoiDung, IdempotencyKey)`: request lặp lại (bấm 2 lần, trình duyệt tự gửi lại) nhận về đúng giao dịch đã tạo và không gửi OTP lần hai. Nếu nhiều request cùng khoá tới đồng thời, request đến sau vướng ràng buộc UNIQUE và cũng nhận lại giao dịch của request đầu. Dùng lại khoá cho một khoản học phí khác trả 409.

**OTP:** sinh ngẫu nhiên 6 chữ số bằng `secrets`, không trùng với OTP còn hiệu lực của giao dịch khác, gắn với một giao dịch, hết hạn sau 5 phút, vô hiệu ngay sau khi dùng, nhập sai 5 lần thì hủy giao dịch.

## 7. Kiểm thử và demo

Script `tests/demo_test.py` gọi REST API (chỉ cần Python 3) và tự đọc OTP từ Mailpit. Trên PowerShell, dùng stack kiểm thử riêng dưới đây; profile này dùng Gateway ở port `18080`, Mailpit ở `18025` và ép email về Mailpit, không phụ thuộc cấu hình Gmail trong `.env`:

```powershell
$compose = @('-p', 'midterm-check', '-f', 'docker-compose.yml', '-f', 'docker-compose.test.yml')
$env:DEMO_GATEWAY_URL = 'http://localhost:18080/api/v1'
$env:DEMO_MAILPIT_URL = 'http://localhost:18025/api/v1'
$env:TEST_COMPOSE_FILES = 'docker-compose.yml;docker-compose.test.yml'
$env:TEST_COMPOSE_PROJECT = 'midterm-check'

docker compose @compose down -v
docker compose @compose up -d --build --wait
python tests/demo_test.py api
python tests/demo_test.py gateway

docker compose @compose down -v; docker compose @compose up -d --wait
python tests/demo_test.py concurrency1

docker compose @compose down -v; docker compose @compose up -d --wait
python tests/demo_test.py concurrency2

docker compose @compose down -v; docker compose @compose up -d --wait
python -m unittest discover -s tests -p 'test_*.py' -v

docker compose @compose down -v
```

Sau khi chạy xong, xoá các biến môi trường ở trên (hoặc mở terminal mới); nếu không, `python tests/demo_test.py ...` sẽ tiếp tục gọi stack kiểm thử ở port 18080 đã bị xoá và báo `ConnectionRefusedError`:

```powershell
Remove-Item Env:DEMO_GATEWAY_URL, Env:DEMO_MAILPIT_URL, Env:TEST_COMPOSE_FILES, Env:TEST_COMPOSE_PROJECT
```

Mỗi lần reset chỉ xóa volume của project kiểm thử `midterm-check`; không chạy `down -v` trên project đang chứa dữ liệu cần giữ.

Có thể chạy bộ kiểm thử tự động bằng:

```bash
python -m unittest discover -s tests -p "test_*.py" -v
```

Bài kiểm thử tích hợp cần stack kiểm thử đang chạy với dữ liệu mẫu mới. Nó tạm dừng rồi khởi động lại `tuition-service`, thanh toán MSSV `524K0011` và xác nhận số dư chỉ bị trừ một lần.

Kết quả mong đợi của `concurrency2`:
```
khiem123: HTTP 200 Thanh toán học phí thành công
nhi123: HTTP 409 Khoản học phí này đã được thanh toán trước đó
Số dư khiem123: 5,000,000 -> 4,250,000
Số dư nhi123: 1,000,000 -> 1,000,000
✅ 1 người thành công (200), người còn lại bị từ chối (409)
```

**Lần theo một giao dịch qua log (tracing):** mỗi dòng log có `rid=<X-Request-ID>`. Lấy ID từ header `X-Request-ID` của response (tab Network của trình duyệt) hoặc từ log của Gateway, rồi lọc:

```powershell
docker compose logs | Select-String "<request-id>"     # PowerShell
docker compose logs | grep "<request-id>"              # bash
```

Ví dụ lọc theo request xác nhận OTP, thấy đủ đường đi Gateway → Payment → Auth → Tuition → Notification:
```
gateway-1              | rid=trace-xac-nhan "POST /api/v1/payments/TXN_4ef1.../confirm HTTP/1.1" 200 upstream=...:8003
payment-service-1      | [payment-service] [rid=trace-xac-nhan] Giao dịch TXN_4ef1...: OTP hợp lệ -> PROCESSING, bắt đầu trừ tiền và gạch nợ
auth-service-1         | [auth-service] [rid=trace-xac-nhan] Giao dịch TXN_4ef1...: trừ 750000.00 của MaNguoiDung=1, số dư còn 4250000.00
auth-service-1         | [auth-service] [rid=trace-xac-nhan] POST /api/v1/users/1/deduct-balance -> 200 (10 ms)
tuition-service-1      | [tuition-service] [rid=trace-xac-nhan] Giao dịch TXN_4ef1...: gạch nợ MaHocPhi=2
tuition-service-1      | [tuition-service] [rid=trace-xac-nhan] POST /api/v1/tuitions/2/pay -> 200 (5 ms)
payment-service-1      | [payment-service] [rid=trace-xac-nhan] Giao dịch TXN_4ef1... -> SUCCESS (MSSV 524K0011, 750000.00)
notification-service-1 | [notification-service] [rid=trace-xac-nhan] POST /api/v1/notifications -> 201 (6 ms)
```

Worker phục hồi giao dịch dùng ID dạng `recovery-...`. Xem log liên tục của toàn hệ thống: `docker compose logs -f`

Xem dữ liệu trực tiếp trong từng database:
```bash
docker compose exec db psql -U root -d auth_db    -c 'SELECT "TenDangNhap", "SoDuKhaDung" FROM "NguoiDung";'
docker compose exec db psql -U root -d tuition_db -c 'SELECT "MSSV", "SoTienPhaiNop", "TrangThai" FROM "HocPhi";'
docker compose exec db psql -U root -d payment_db -c 'SELECT "MaGiaoDich", "MSSV", "TrangThai" FROM "GiaoDich";'
```

## 8. Cấu hình gửi email qua Gmail

Mặc định email được gửi vào Mailpit để chạy được ngay mà không cần tài khoản. Để gửi email thật qua Gmail:

1. Bật xác minh 2 bước cho tài khoản Gmail, sau đó tạo **Mật khẩu ứng dụng** (App Password) tại https://myaccount.google.com/apppasswords.
2. Tạo file `.env` ở thư mục gốc (cạnh `docker-compose.yml`) với nội dung:
   ```env
   SMTP_HOST=smtp.gmail.com
   SMTP_PORT=587
   SMTP_USE_TLS=true
   SMTP_USER=tai.khoan@gmail.com
   SMTP_PASSWORD=xxxx xxxx xxxx xxxx
   MAIL_FROM=iBanking TDTU <tai.khoan@gmail.com>
   ```
3. Chạy lại `docker compose up -d` để Notification Service nhận cấu hình mới.

Email của các tài khoản mẫu là email sinh viên TDTU (`@student.tdtu.edu.vn`). Nếu gửi bằng **tài khoản sinh viên TDTU**, lưu ý trường chỉ cho phép gửi tới địa chỉ trong hệ thống `@student.tdtu.edu.vn`; gửi ra ngoài sẽ bị từ chối (lỗi SMTP 550) và giao diện báo "Không gửi được email OTP".

Các biến SMTP được truyền cho **Notification Service** (service duy nhất gửi email). File `.env` và các file override `.env.*` được loại khỏi Git. Không commit mật khẩu ứng dụng Gmail hoặc secret thật.

| Biến môi trường | Mặc định | Ý nghĩa |
|---|---|---|
| `SMTP_HOST` / `SMTP_PORT` | `mailpit` / `1025` | Máy chủ SMTP (Gmail: `smtp.gmail.com` / `587`) |
| `SMTP_USE_TLS` | `false` | Bật STARTTLS (Gmail: `true`) |
| `SMTP_USER` / `SMTP_PASSWORD` | (trống) | Tài khoản Gmail và App Password |
| `MAIL_FROM` | `iBanking TDTU <no-reply@ibanking.local>` | Người gửi |
| `EMAIL_PROVIDER` | `smtp` | Adapter gửi email: `smtp` (Mailpit/Gmail) hoặc `console` (chỉ in ra log) |
| `JWT_SECRET` | khóa dev | Khóa ký JWT, dùng chung cho Auth/Tuition/Payment |
| `INTERNAL_API_KEY` | khóa dev | Khóa gọi API nội bộ giữa các service |

## 9. Cấu trúc thư mục

```
├── gateway/nginx.conf       # API Gateway: định tuyến /api/v1, chặn API nội bộ, X-Request-ID
├── backend/
│   ├── shared/              # Code dùng chung cho mọi service
│   │   ├── service_app.py   # Khởi tạo FastAPI: Swagger qua Gateway, lỗi validate trả 400
│   │   ├── security.py      # Xác thực JWT và khoá API nội bộ (X-Internal-Key)
│   │   └── observability.py # Logging & tracing (X-Request-ID)
│   ├── auth_service/        # FastAPI: đăng nhập, JWT, người dùng, số dư
│   ├── tuition_service/     # FastAPI: sinh viên, học phí
│   ├── payment_service/     # FastAPI: giao dịch, OTP, điều phối thanh toán (Saga)
│   └── notification_service/ # FastAPI: Adapter gửi thông báo (main.py: API + mẫu, senders.py: adapter)
├── frontend/                # Giao diện web, được Gateway phục vụ tại http://localhost
│   ├── login.html           # Đăng nhập
│   ├── tuition.html         # Thanh toán học phí (người nộp, học phí, thanh toán)
│   ├── payment.html         # Nhập OTP và kết quả giao dịch
│   ├── history.html         # Lịch sử giao dịch
│   ├── common.js            # Gọi API, xử lý JWT, hàm dùng chung
│   └── style.css
├── tests/demo_test.py       # Script demo luồng chính và concurrency
├── tests/test_saga_recovery.py # Kiểm thử tự động idempotency và phục hồi saga
├── tests/DEMO_RESULTS.md    # Tóm tắt kết quả demo và tích hợp đã chạy
├── init.sql                 # Tạo 3 database, bảng, ràng buộc, dữ liệu mẫu
├── docker-compose.yml
├── docker-compose.dev.yml   # Tuỳ chọn: mở port từng service/DB để debug
├── docker-compose.test.yml  # Stack kiểm thử cô lập (Gateway :18080, Mailpit :18025)
└── .env                     # Cấu hình local, không commit lên Git
```
