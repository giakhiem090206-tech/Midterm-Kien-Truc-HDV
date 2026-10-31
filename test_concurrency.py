"""
KỊCH BẢN KIỂM THỬ TỰ ĐỘNG E2E & CONCURRENCY (RACE CONDITION)
Phân hệ Đóng học phí TDTU iBanking - Kiến Trúc Hướng Dịch Vụ (504070)

Chạy trực tiếp bằng lệnh:
    python test_concurrency.py
"""

import os
import sys
import json
import urllib.request
import urllib.error
from concurrent.futures import ThreadPoolExecutor, as_completed

# Đảm bảo hiển thị tiếng Việt có dấu trên Windows Terminal / PowerShell không bị lỗi UnicodeEncodeError
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

AUTH_URL = os.getenv("AUTH_SERVICE_URL", "http://localhost:8001")
TUITION_URL = os.getenv("TUITION_SERVICE_URL", "http://localhost:8002")
PAYMENT_URL = os.getenv("PAYMENT_SERVICE_URL", "http://localhost:8003")


def http_request(method: str, url: str, body: dict = None, headers: dict = None):
    req_headers = {"Content-Type": "application/json"}
    if headers:
        req_headers.update(headers)
    data = json.dumps(body).encode("utf-8") if body is not None else None
    req = urllib.request.Request(url, data=data, headers=req_headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return resp.status, json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        err_body = e.read().decode("utf-8")
        try:
            return e.code, json.loads(err_body)
        except Exception:
            return e.code, {"detail": err_body}


def print_banner(title: str):
    print("\n" + "=" * 75)
    print(f"  {title}")
    print("=" * 75)


def reset_data():
    status, data = http_request("POST", f"{PAYMENT_URL}/api/v1/payments/demo/reset")
    assert status == 200, f"Không thể reset dữ liệu mẫu: {data}"
    print("[OK] Đã khôi phục dữ liệu mẫu về trạng thái chuẩn ban đầu.")


def test_scenario_1_same_account_concurrent_payments():
    """
    TÌNH HUỐNG 1 (Đề bài mục 5 & Rubric mục 6):
    Nhiều giao dịch đồng thời trên cùng một tài khoản:
    - Tài khoản `phuc123` có số dư khả dụng: 10,000,000 VNĐ.
    - Khởi tạo đồng thời 2 giao dịch cho 2 sinh viên:
      + Giao dịch A: Đóng cho MSSV 524K0011 (5,300,000 VNĐ)
      + Giao dịch B: Đóng cho MSSV 523V0005 (5,300,000 VNĐ)
    - Tổng 2 khoản là 10,600,000 VNĐ (> 10,000,000 VNĐ).
    - Khi bắn xác nhận OTP đồng thời (Concurrency):
      + Hệ thống dùng Pessimistic Locking (SELECT ... FOR UPDATE) khóa dòng `nguoi_dung`.
      + Chỉ ĐÚNG 1 giao dịch thành công (SUCCESS), giao dịch còn lại bị từ chối (400 Bad Request - FAILED) do số dư còn lại (4,700,000 VNĐ) không đủ.
      + Số dư cuối cùng không bị âm (>= 0).
    """
    print_banner("TEST TÌNH HUỐNG 1: NHIỀU GIAO DỊCH ĐỒNG THỜI TRÊN CÙNG 1 TÀI KHOẢN (CHỐNG ÂM SỐ DƯ)")
    reset_data()

    # 1. Đăng nhập tài khoản phuc123
    status, login_data = http_request("POST", f"{AUTH_URL}/api/v1/auth/login", {"username": "phuc123", "password": "123456"})
    assert status == 200, f"Lỗi đăng nhập: {login_data}"
    user_id = login_data["MaNguoiDung"]
    initial_balance = float(login_data["SoDuKhaDung"])
    print(f"[1] Đăng nhập 'phuc123' (ID={user_id}) | Số dư ban đầu: {initial_balance:,.0f} VNĐ")

    # 2. Tra cứu 2 khoản học phí
    s_hp1, hp1 = http_request("GET", f"{TUITION_URL}/api/v1/tuitions/524K0011")
    s_hp2, hp2 = http_request("GET", f"{TUITION_URL}/api/v1/tuitions/523V0005")
    assert s_hp1 == 200 and s_hp2 == 200, f"Không tìm thấy học phí: {hp1} | {hp2}"
    print(f"[2] Khoản học phí 1: MSSV {hp1['MSSV']} - {hp1['SoTienPhaiNop']:,.0f} VNĐ")
    print(f"[2] Khoản học phí 2: MSSV {hp2['MSSV']} - {hp2['SoTienPhaiNop']:,.0f} VNĐ")

    # 3. Khởi tạo cả 2 giao dịch (lúc này số dư 10tr >= 5.3tr nên cả 2 đều nhận được OTP)
    s1, init1 = http_request("POST", f"{PAYMENT_URL}/api/v1/payments/initiate", {"MaNguoiDung": user_id, "MaHocPhi": hp1["MaHocPhi"]})
    s2, init2 = http_request("POST", f"{PAYMENT_URL}/api/v1/payments/initiate", {"MaNguoiDung": user_id, "MaHocPhi": hp2["MaHocPhi"]})
    assert s1 == 201 and s2 == 201, f"Khởi tạo thất bại: {init1} | {init2}"
    print(f"[3] Đã sinh OTP cho GD 1 ({init1['MaGiaoDich']}): OTP = {init1['otp_demo']}")
    print(f"[3] Đã sinh OTP cho GD 2 ({init2['MaGiaoDich']}): OTP = {init2['otp_demo']}")

    # 4. Bắn 2 request confirm OTP ĐỒNG THỜI (Multi-threading)
    print("[4] Đang bắn ĐỒNG THỜI 2 request xác nhận OTP...")
    payloads = [
        {"MaGiaoDich": init1["MaGiaoDich"], "otp": init1["otp_demo"]},
        {"MaGiaoDich": init2["MaGiaoDich"], "otp": init2["otp_demo"]},
    ]

    results = []
    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [
            executor.submit(http_request, "POST", f"{PAYMENT_URL}/api/v1/payments/confirm", p)
            for p in payloads
        ]
        for f in as_completed(futures):
            results.append(f.result())

    for code, resp in results:
        print(f"    -> Kết quả HTTP {code}: {resp}")

    success_count = sum(1 for code, _ in results if code == 200)
    failed_count = sum(1 for code, _ in results if code == 400)

    # 5. Kiểm tra số dư cuối cùng của phuc123
    _, user_after = http_request("GET", f"{AUTH_URL}/api/v1/users/{user_id}")
    final_balance = float(user_after["available_balance"])
    print(f"[5] Số dư của 'phuc123' sau khi 2 giao dịch chạy đồng thời: {final_balance:,.0f} VNĐ")

    assert success_count == 1 and failed_count == 1, "LỖI CONCURRENCY: Phải có đúng 1 GD thành công và 1 GD bị chặn!"
    assert final_balance >= 0, "LỖI CONCURRENCY: Số dư bị âm!"
    print("[PASS] KẾT LUẬN TÌNH HUỐNG 1: Đảm bảo chống chi tiêu vượt số dư khả dụng.")


def test_scenario_2_multiple_accounts_same_tuition():
    """
    TÌNH HUỐNG 2 (Đề bài mục 5 & Rubric mục 6):
    Nhiều tài khoản cùng thanh toán một khoản học phí:
    - Hai người dùng `khiem123` và `phuc123` cùng thanh toán cho 1 MSSV `524K0011` (5,300,000 VNĐ).
    - Cả hai khởi tạo giao dịch và nhận mã OTP riêng.
    - Khi cả hai bấm xác nhận OTP ĐỒNG THỜI:
      + Hệ thống dùng Pessimistic Locking (SELECT ... FOR UPDATE) khóa dòng `hoc_phi`.
      + Khoản học phí của `524K0011` chỉ được thanh toán thành công ĐÚNG 1 LẦN.
      + Chỉ 1 người bị trừ tiền, người còn lại nhận thông báo lỗi 400 và giữ nguyên số dư.
    """
    print_banner("TEST TÌNH HUỐNG 2: NHIỀU TÀI KHOẢN ĐỒNG THỜI ĐÓNG CÙNG 1 HỌC PHÍ (CHỐNG ĐÓNG TRÙNG)")
    reset_data()

    # 1. Đăng nhập 2 tài khoản
    _, u1 = http_request("POST", f"{AUTH_URL}/api/v1/auth/login", {"username": "khiem123", "password": "123456"})
    _, u2 = http_request("POST", f"{AUTH_URL}/api/v1/auth/login", {"username": "phuc123", "password": "123456"})
    user1_id, user2_id = u1["MaNguoiDung"], u2["MaNguoiDung"]
    u1_before = float(u1["SoDuKhaDung"])
    u2_before = float(u2["SoDuKhaDung"])

    # 2. Cùng tra cứu MSSV 524K0011
    _, hp = http_request("GET", f"{TUITION_URL}/api/v1/tuitions/524K0011")
    ma_hoc_phi = hp["MaHocPhi"]
    tuition_amount = float(hp["SoTienPhaiNop"])
    print(f"[1] Hai tài khoản 'khiem123' và 'phuc123' cùng đóng cho MSSV {hp['MSSV']} ({tuition_amount:,.0f} VNĐ)")

    # 3. Cả 2 cùng khởi tạo giao dịch và nhận OTP riêng
    s1, init1 = http_request("POST", f"{PAYMENT_URL}/api/v1/payments/initiate", {"MaNguoiDung": user1_id, "MaHocPhi": ma_hoc_phi})
    s2, init2 = http_request("POST", f"{PAYMENT_URL}/api/v1/payments/initiate", {"MaNguoiDung": user2_id, "MaHocPhi": ma_hoc_phi})
    assert s1 == 201 and s2 == 201, f"Khởi tạo thất bại: {init1} | {init2}"
    print(f"[2] GD của khiem123: {init1['MaGiaoDich']} (OTP: {init1['otp_demo']})")
    print(f"[2] GD của phuc123:  {init2['MaGiaoDich']} (OTP: {init2['otp_demo']})")

    # 4. Bắn 2 request confirm OTP ĐỒNG THỜI
    print("[3] Đang bắn ĐỒNG THỜI 2 request xác nhận OTP cho cùng MSSV 524K0011...")
    payloads = [
        {"MaGiaoDich": init1["MaGiaoDich"], "otp": init1["otp_demo"]},
        {"MaGiaoDich": init2["MaGiaoDich"], "otp": init2["otp_demo"]},
    ]

    results = []
    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [
            executor.submit(http_request, "POST", f"{PAYMENT_URL}/api/v1/payments/confirm", p)
            for p in payloads
        ]
        for f in as_completed(futures):
            results.append(f.result())

    for code, resp in results:
        print(f"    -> Kết quả HTTP {code}: {resp}")

    success_count = sum(1 for code, _ in results if code == 200)
    failed_count = sum(1 for code, _ in results if code == 400)

    # 5. Kiểm tra số dư 2 tài khoản và trạng thái học phí
    _, u1_after = http_request("GET", f"{AUTH_URL}/api/v1/users/{user1_id}")
    _, u2_after = http_request("GET", f"{AUTH_URL}/api/v1/users/{user2_id}")
    _, hp_after = http_request("GET", f"{TUITION_URL}/api/v1/tuitions/524K0011")

    u1_final = float(u1_after["available_balance"])
    u2_final = float(u2_after["available_balance"])

    print(f"[4] Số dư khiem123 sau GD: {u1_final:,.0f} VNĐ (Ban đầu: {u1_before:,.0f} VNĐ)")
    print(f"[4] Số dư phuc123 sau GD:  {u2_final:,.0f} VNĐ (Ban đầu: {u2_before:,.0f} VNĐ)")
    print(f"[4] Trạng thái học phí 524K0011: {hp_after['TrangThai']}")

    total_deducted = (u1_before - u1_final) + (u2_before - u2_final)
    assert success_count == 1 and failed_count == 1, "LỖI CONCURRENCY: Phải có đúng 1 người đóng thành công!"
    assert abs(total_deducted - tuition_amount) < 1.0, (
        f"LỖI CONCURRENCY: Tổng số tiền bị trừ ({total_deducted:,.0f}) không đúng bằng 1 lần học phí ({tuition_amount:,.0f})!"
    )
    assert hp_after["TrangThai"] == "DA_DONG", "Trạng thái học phí phải là DA_DONG!"
    print("[PASS] KẾT LUẬN TÌNH HUỐNG 2: Khoản học phí chỉ được thanh toán thành công đúng 1 lần.")


def test_scenario_3_idempotency_key_and_webhook():
    """
    TÌNH HUỐNG 3 (Theo sơ đồ trên bảng của Giảng viên - Idempotency-Key & Webhook Callback):
    - Khi Client/Service A gửi lặp lại cùng một Request với cùng Header `Idempotency-Key (IK)`
      (do mạng chập chờn retry hoặc người dùng bấm đúp):
      + Hệ thống nhận diện `Idempotency-Key`, KHÔNG tạo giao dịch mới và KHÔNG trừ tiền lần 2,
        mà trả về đúng kết quả đã lưu (`idempotent_replay = True`).
    """
    print_banner("TEST TÌNH HUỐNG 3: IDEMPOTENCY-KEY (IK) & WEBHOOK CALLBACK")
    reset_data()

    _, u1 = http_request("POST", f"{AUTH_URL}/api/v1/auth/login", {"username": "khiem123", "password": "123456"})
    user_id = u1["MaNguoiDung"]
    _, hp = http_request("GET", f"{TUITION_URL}/api/v1/tuitions/524V0007")

    ik_header = {"Idempotency-Key": "IK_DEMO_TEST_001"}
    s1, r1 = http_request("POST", f"{PAYMENT_URL}/api/v1/payments/initiate", {"MaNguoiDung": user_id, "MaHocPhi": hp["MaHocPhi"]}, headers=ik_header)
    s2, r2 = http_request("POST", f"{PAYMENT_URL}/api/v1/payments/initiate", {"MaNguoiDung": user_id, "MaHocPhi": hp["MaHocPhi"]}, headers=ik_header)

    print(f"[1] Lần gửi 1 (IK=IK_DEMO_TEST_001): MaGiaoDich={r1['MaGiaoDich']} | idempotent_replay={r1.get('idempotent_replay')}")
    print(f"[2] Lần gửi 2 (Cùng IK):             MaGiaoDich={r2['MaGiaoDich']} | idempotent_replay={r2.get('idempotent_replay')}")

    assert r1["MaGiaoDich"] == r2["MaGiaoDich"], "LỖI IDEMPOTENCY: Cùng Idempotency-Key nhưng sinh ra 2 giao dịch khác nhau!"
    assert r2.get("idempotent_replay") is True, "LỖI IDEMPOTENCY: Lần gọi lại phải đánh dấu idempotent_replay = True!"

    # Kiểm thử Webhook Callback kèm Idempotency-Key
    wh_ik = {"Idempotency-Key": "IK_WEBHOOK_001"}
    _, wh1 = http_request("POST", f"{PAYMENT_URL}/api/v1/payments/webhook/callback", {"MaGiaoDich": r1["MaGiaoDich"]}, headers=wh_ik)
    _, wh2 = http_request("POST", f"{PAYMENT_URL}/api/v1/payments/webhook/callback", {"MaGiaoDich": r1["MaGiaoDich"]}, headers=wh_ik)
    print(f"[3] Webhook Callback lần 1: {wh1}")
    print(f"[4] Webhook Callback lần 2 (Replay): {wh2}")
    assert wh2.get("idempotent_replay") is True
    print("[PASS] KẾT LUẬN TÌNH HUỐNG 3: Idempotency-Key (IK) & Webhook Callback hoạt động chính xác!")


if __name__ == "__main__":
    test_scenario_1_same_account_concurrent_payments()
    test_scenario_2_multiple_accounts_same_tuition()
    test_scenario_3_idempotency_key_and_webhook()
    reset_data()
    print("\n[SUCCESS] TẤT CẢ KỊCH BẢN CONCURRENCY, TRANSACTION & IDEMPOTENCY-KEY ĐỀU VƯỢT QUA THÀNH CÔNG!")
