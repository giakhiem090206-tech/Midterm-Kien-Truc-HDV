# Kết quả chạy kiểm thử

Ngày chạy: 2026-10-30, trên phiên bản có API Gateway, Notification Service, Idempotency-Key và logging/tracing.

Môi trường: stack kiểm thử cô lập `midterm-check` (`docker-compose.test.yml`): Gateway ở port 18080, Mailpit ở 18025, email luôn vào Mailpit (không dùng cấu hình Gmail trong `.env`). Database được reset về dữ liệu mẫu trước mỗi kịch bản. Cách chạy lại: README mục 7.

| Lệnh | Kết quả | Nội dung kiểm tra |
|---|---|---|
| `python tests/demo_test.py api` | ĐẠT | Đăng nhập, JWT (401 khi thiếu/giả token), Gateway chặn API nội bộ (404), `X-Request-ID` trả về đúng, tra cứu học phí (200/404), số dư không đủ (400), validation (400), Idempotency-Key (gửi lại cùng khoá trả lại giao dịch cũ, chỉ 1 email OTP, dùng khoá cho yêu cầu khác trả 409), OTP sai/sai định dạng (400), xác nhận giao dịch của người khác (403), OTP đúng (200), dùng lại OTP (409), lịch sử giao dịch, email OTP + email xác nhận |
| `python tests/demo_test.py gateway` | ĐẠT | Trang chủ và Swagger của 3 service xem được qua Gateway; duyệt mọi API trong openapi.json: 7 API công khai tới được service, 5 API nội bộ bị Gateway chặn |
| `python tests/demo_test.py concurrency1` | ĐẠT | `phuc123` (15.500.000) đồng thời thanh toán 750.000 + 15.000.000: đúng 1 giao dịch thành công, giao dịch còn lại bị từ chối vì không đủ số dư, số dư không âm |
| `python tests/demo_test.py concurrency2` | ĐẠT | `khiem123` và `nhi123` đồng thời thanh toán MSSV 524K0011: 1 người nhận 200, người còn lại nhận 409 và được hoàn tiền (số dư không đổi) |
| `python tests/test_saga_recovery.py` | ĐẠT | Tắt Tuition Service giữa lúc thanh toán: giao dịch ở `PROCESSING`, tự phục hồi thành `SUCCESS` khi service chạy lại, số dư chỉ bị trừ đúng một lần |

Log của toàn bộ lần chạy không có traceback.
