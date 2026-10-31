"""
KỊCH BẢN KIỂM THỬ TỰ ĐỘNG E2E & CONCURRENCY (RACE CONDITION)
Phân hệ Đóng học phí TDTU iBanking - Kiến Trúc Hướng Dịch Vụ (504070)

Chạy trực tiếp bằng lệnh:
    python test_concurrency.py
"""

import json
import urllib.request
import urllib.error
from concurrent.futures import ThreadPoolExecutor, as_completed

AUTH_URL = "http://localhost:8001"
TUITION_URL = "http://localhost:8002"
PAYMENT_URL = "http://localhost:8003"


def http_request(method: str, url: str, body: dict = None, headers: dict = None):
    req_headers = {"Content-Type": "application/json"}
    if headers:
        req_headers.update(headers)
    data = json.dumps(body).encode("utf-8") if body is not None else None
    req = urllib.request.Request(url, data=data, headers=req_headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
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
    print("[✓] Đã khôi phục dữ liệu mẫu về trạng thái chuẩn ban đầu.")


def test_scenario_1_same_account_concurrent_payments():
    """
    TÌNH HUỐNG 1 (Đề bài mục 5 & Rubric mục 6):
    Nhiều giao dịch đồng thời trên cùng một tài khoản:
    - Tài khoản `phuc123` có số dư khả dụng: 10,000,000 VNĐ.
    - Khởi tạo đồng thời 2 giao dịch cho 2 sinh viên:
      + Giao dịch A: Đóng cho MSSV 524K0001 (Số tiền: 7,500,000 VNĐ)
      + Giao dịch B: Đóng cho MSSV 524K0005 (Số tiền: 8,000,000 VNĐ)
    - Tổng 2 khoản là 15,500,000 VNĐ (> 10,000,000 VNĐ).
    - Khi bắn xác nhận OTP đồng thời (Concurrency):
      + Hệ thống dùng Pessimistic Locking (SELECT ... FOR UPDATE) khóa dòng `nguoi_dung`.
      + Chỉ ĐÚNG 1 giao dịch thành công (SUCCESS), giao dịch còn lại bị từ chối (400 Bad Request - FAILED) do số dư còn lại không đủ.
      + Số dư cuối cùng không bị âm (>= 0).
    """
    print_banner("TEST TÌNH HUỐNG 1: NHIỀU GIAO DỊCH ĐỒNG THỜI TRÊN CÙNG 1 TÀI KHOẢN (CHỐNG ÂM SỐ DƯ)")
    reset_data()

    # 1. Đăng nhập tài khoản phuc123 (Số dư 10,000,000 VNĐ)
    status, login_data = http_request("POST", f"{AUTH_URL}/api/v1/auth/login", {"username": "phuc123", "password": "123456"})
    assert status == 200, f"Lỗi đăng nhập: {login_data}"
    user_id = login_data["MaNguoiDung"]
    print(f"[1] Đăng nhập 'phuc123' (ID={user_id}) | Số dư ban đầu: {login_data['SoDuKhaDung']:,.0f} VNĐ")

    # 2. Tra cứu 2 khoản học phí
    _, hp1 = http_request("GET", f"{TUITION_URL}/api/v1/tuitions/524K0011")
    _, hp2 = http_request("GET", f"{TUITION_URL}/api/v1/tuitions/523V0005")
    print(f"[2] Khoản học phí 1: MSSV {hp1['MSSV']} - {hp1['SoTienPhaiNop']:,.0f} VNĐ")
    print(f"[2] Khoản học phí 2: MSSV {hp2['MSSV']} - {hp2['SoTienPhaiNop']:,.0f} VNĐ")

    # 3. Khởi tạo cả 2 giao dịch (lúc này số dư 10tr vẫn >= 7.5tr và >= 8.0tr nên cả 2 đều nhận được OTP)
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
    print(f"[5] Số dư của 'phuc123' sau khi 2 giao dịch chạy đồng thời: {user_after['available_balance']:,.0f} VNĐ")

    assert success_count == 1 and failed_count == 1, "LỖI CONCURRENCY: Phải có đúng 1 GD thành công và 1 GD bị chặn!"
    assert user_after["available_balance"] >= 0, "LỖI CONCURRENCY: Số dư bị âm!"
    print("[✓] KẾT LUẬN TÌNH HUỐNG 1: PASS! Đảm bảo chống chi tiêu vượt số dư khả dụng.")


def test_scenario_2_multiple_accounts_same_tuition():
    """
    TÌNH HUỐNG 2 (Đề bài mục 5 & Rubric mục 6):
    Nhiều tài khoản cùng thanh toán một khoản học phí:
    - Hai người dùng `khiem123` (20tr VNĐ) và `phuc123` (10tr VNĐ) cùng thanh toán cho 1 MSSV `524K0001` (7,500,000 VNĐ).
    - Cả hai khởi tạo giao dịch và nhận mã OTP riêng.
    - Khi cả hai bấm xác nhận OTP ĐỒNG THỜI:
      + Hệ thống dùng Pessimistic Locking (SELECT ... FOR UPDATE) khóa dòng `hoc_phi`.
      + Khoản học phí của `524K0001` chỉ được thanh toán thành công ĐÚNG 1 LẦN.
      + Chỉ 1 người bị trừ tiền, người còn lại nhận thông báo lỗi 400 và giữ nguyên số dư.
    """
    print_banner("TEST TÌNH HUỐNG 2: NHIỀU TÀI KHOẢN ĐỒNG THỜI ĐÓNG CÙNG 1 HỌC PHÍ (CHỐNG ĐÓNG TRÙNG)")
    reset_data()

    # 1. Đăng nhập 2 tài khoản
    _, u1 = http_request("POST", f"{AUTH_URL}/api/v1/auth/login", {"username": "khiem123", "password": "123456"})
    _, u2 = http_request("POST", f"{AUTH_URL}/api/v1/auth/login", {"username": "phuc123", "password": "123456"})
    user1_id, user2_id = u1["MaNguoiDung"], u2["MaNguoiDung"]

    # 2. Cùng tra cứu MSSV 524K0011 (7,500,000 VNĐ)
    _, hp = http_request("GET", f"{TUITION_URL}/api/v1/tuitions/524K0011")
    ma_hoc_phi = hp["MaHocPhi"]
    print(f"[1] Hai tài khoản 'khiem123' và 'phuc123' cùng đóng cho MSSV {hp['MSSV']} ({hp['SoTienPhaiNop']:,.0f} VNĐ)")

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

    print(f"[4] Số dư khiem123 sau GD: {u1_after['available_balance']:,.0f} VNĐ (Ban đầu: 20,000,000 VNĐ)")
    print(f"[4] Số dư phuc123 sau GD:  {u2_after['available_balance']:,.0f} VNĐ (Ban đầu: 10,000,000 VNĐ)")
    print(f"[4] Trạng thái học phí 524K0011: {hp_after['TrangThai']}")

    total_deducted = (20000000.0 - u1_after["available_balance"]) + (10000000.0 - u2_after["available_balance"])
    assert success_count == 1 and failed_count == 1, "LỖI CONCURRENCY: Phải có đúng 1 người đóng thành công!"
    assert total_deducted == 7500000.0, f"LỖI CONCURRENCY: Tổng số tiền bị trừ ({total_deducted}) không đúng bằng 1 lần học phí!"
    assert hp_after["TrangThai"] == "DA_DONG", "Trạng thái học phí phải là DA_DONG!"
    print("[✓] KẾT LUẬN TÌNH HUỐNG 2: PASS! Khoản học phí chỉ được thanh toán thành công đúng 1 lần.")


if __name__ == "__main__":
    test_scenario_1_same_account_concurrent_payments()
    test_scenario_2_multiple_accounts_same_tuition()
    reset_data()
    print("\n🎉 TẤT CẢ KỊCH BẢN CONCURRENCY & TRANSACTION ĐỀU VƯỢT QUA THÀNH CÔNG!")

