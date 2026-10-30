"""
Script demo / kiểm thử hệ thống qua REST API (chỉ dùng thư viện chuẩn của Python).

Cách chạy (sau khi `docker compose up -d`):
    python tests/demo_test.py api            # luồng chính + các mã lỗi HTTP
    python tests/demo_test.py concurrency1   # nhiều giao dịch đồng thời trên cùng 1 tài khoản
    python tests/demo_test.py concurrency2   # nhiều tài khoản cùng thanh toán 1 khoản học phí
    python tests/demo_test.py gateway        # Swagger qua Gateway + Gateway chỉ mở API công khai

Mỗi kịch bản cần dữ liệu ban đầu, reset trước khi chạy:
    docker compose down -v; docker compose up -d --wait
"""
import json
import os
import re
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request

sys.stdout.reconfigure(encoding="utf-8")

# Mọi API đi qua API Gateway; stack kiểm thử dùng DEMO_GATEWAY_URL=http://localhost:18080/api/v1
GATEWAY = os.getenv("DEMO_GATEWAY_URL", "http://localhost/api/v1")
AUTH = TUITION = PAYMENT = GATEWAY
MAILPIT = os.getenv("DEMO_MAILPIT_URL", "http://localhost:8025/api/v1")

failures = 0


def call(method, url, body=None, token=None, headers=None):
    headers = {"Content-Type": "application/json", **(headers or {})}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=30) as res:
            return res.status, json.loads(res.read() or "null")
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read() or "null")


def check(name, status, expected, data=None):
    global failures
    ok = status == expected
    failures += 0 if ok else 1
    detail = data.get("detail", "") if isinstance(data, dict) else ""
    print(f"  {'✅' if ok else '❌'} {name}: HTTP {status} (mong đợi {expected}) {detail}")


def check_true(name, condition):
    global failures
    failures += 0 if condition else 1
    print(f"  {'✅' if condition else '❌'} {name}")


def login(username):
    status, data = call("POST", f"{AUTH}/auth/login", {"username": username, "password": "123456"})
    assert status == 200, data
    return data["access_token"]


def balance(token):
    return call("GET", f"{AUTH}/users/me", token=token)[1]["available_balance"]


def tuition_id(token, mssv):
    return call("GET", f"{TUITION}/tuitions/{mssv}", token=token)[1]["MaHocPhi"]


def create_payment(token, ma_hoc_phi, idempotency_key=None):
    headers = {"Idempotency-Key": idempotency_key} if idempotency_key else None
    return call("POST", f"{PAYMENT}/payments", {"MaHocPhi": ma_hoc_phi}, token, headers)


def confirm(token, txn, otp):
    return call("POST", f"{PAYMENT}/payments/{txn}/confirm", {"otp": otp}, token)


def otp_from_mailpit(txn):
    """Đọc mã OTP trong email (Mailpit) của giao dịch"""
    query = urllib.parse.quote(txn)
    for _ in range(20):
        for msg in call("GET", f"{MAILPIT}/search?query={query}")[1]["messages"]:
            html = call("GET", f"{MAILPIT}/message/{msg['ID']}")[1]["HTML"]
            found = re.search(r'letter-spacing: 8px;">(\d{6})<', html)
            if found:
                return found.group(1)
        time.sleep(0.25)
    raise RuntimeError(f"Không tìm thấy email OTP của giao dịch {txn}")


def run_concurrently(*funcs):
    """Chạy các hàm cùng lúc (dùng Barrier để các request xuất phát đồng thời)"""
    results = [None] * len(funcs)
    barrier = threading.Barrier(len(funcs))

    def worker(i, f):
        barrier.wait()
        results[i] = f()

    threads = [threading.Thread(target=worker, args=(i, f)) for i, f in enumerate(funcs)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    return results


def scenario_api():
    print("=== Luồng chính & mã lỗi HTTP ===")
    s, d = call("POST", f"{AUTH}/auth/login", {"username": "phuc123", "password": "sai"})
    check("Đăng nhập sai mật khẩu", s, 401, d)
    s, d = call("POST", f"{AUTH}/auth/login", {"username": "", "password": ""})
    check("Đăng nhập thiếu dữ liệu", s, 400, d)
    s, d = call("GET", f"{AUTH}/users/me")
    check("Xem tài khoản khi chưa đăng nhập", s, 401, d)
    s, d = call("GET", f"{AUTH}/users/me", token="token-gia-mao")
    check("Token giả mạo", s, 401, d)
    s, d = call("POST", f"{GATEWAY}/users/1/deduct-balance", {"amount": 1000, "transaction_id": "x"})
    check("Gateway chặn API nội bộ trừ tiền", s, 404, d)
    s, d = call("POST", f"{GATEWAY}/tuitions/2/pay", {"transaction_id": "x"})
    check("Gateway chặn API nội bộ gạch nợ", s, 404, d)
    s, d = call("POST", f"{GATEWAY}/notifications", {"to": "a@b.c", "template": "OTP", "data": {}})
    check("Gateway chặn Notification Service", s, 404, d)

    req = urllib.request.Request(f"{GATEWAY}/auth/login", method="POST",
                                 data=json.dumps({"username": "khiem123", "password": "123456"}).encode(),
                                 headers={"Content-Type": "application/json", "X-Request-ID": "demo-trace-123"})
    with urllib.request.urlopen(req, timeout=30) as res:
        check_true("Tracing: response trả lại đúng X-Request-ID client gửi",
                   res.headers.get("X-Request-ID") == "demo-trace-123")
    with urllib.request.urlopen(f"{GATEWAY}/payments/docs", timeout=30) as res:
        check_true("Swagger của Payment xem được qua Gateway", res.status == 200)

    phuc, khiem, nhi = login("phuc123"), login("khiem123"), login("nhi123")
    s, d = call("GET", f"{AUTH}/users/me", token=phuc)
    check("Xem thông tin tài khoản phuc123", s, 200, d)
    print(f"     {d}")

    s, d = call("GET", f"{TUITION}/tuitions/999999", token=phuc)
    check("Tra cứu MSSV không tồn tại", s, 404, d)
    s, d = call("GET", f"{TUITION}/tuitions/524K0006", token=phuc)
    check("Tra cứu MSSV đã đóng học phí", s, 404, d)
    s, d = call("GET", f"{TUITION}/tuitions/524K0011", token=phuc)
    check("Tra cứu MSSV 524K0011", s, 200, d)
    print(f"     {d}")

    s, d = create_payment(nhi, tuition_id(nhi, "523V0005"))
    check("nhi123 (1tr) thanh toán 15tr", s, 400, d)
    s, d = create_payment(phuc, -1)
    check("Tạo giao dịch với MaHocPhi không hợp lệ", s, 400, d)

    key = f"demo-{time.time_ns()}"
    s, d = create_payment(phuc, tuition_id(phuc, "524K0011"), key)
    check("phuc123 tạo giao dịch thanh toán 524K0011 (kèm Idempotency-Key)", s, 201, d)
    txn = d["transaction_id"]
    otp = otp_from_mailpit(txn)
    print(f"     OTP đọc từ email: {otp}")

    s, d = create_payment(phuc, tuition_id(phuc, "524K0011"), key)
    check_true("Gửi lại cùng Idempotency-Key -> trả lại đúng giao dịch cũ",
               s == 201 and d.get("transaction_id") == txn)
    otp_mails = [m for m in call("GET", f"{MAILPIT}/search?query={txn}")[1]["messages"] if "OTP" in m["Subject"]]
    check_true(f"Chỉ gửi 1 email OTP cho giao dịch (đếm được {len(otp_mails)})", len(otp_mails) == 1)
    s, d = create_payment(phuc, tuition_id(phuc, "523V0005"), key)
    check("Dùng lại Idempotency-Key cho khoản học phí khác", s, 409, d)

    wrong = "000000" if otp != "000000" else "111111"
    s, d = confirm(phuc, txn, wrong)
    check("Nhập sai OTP", s, 400, d)
    s, d = confirm(phuc, txn, "12ab")
    check("OTP sai định dạng", s, 400, d)
    s, d = confirm(khiem, txn, otp)
    check("Người khác xác nhận giao dịch của phuc123", s, 403, d)
    s, d = confirm(phuc, txn, otp)
    check("Nhập đúng OTP", s, 200, d)
    s, d = confirm(phuc, txn, otp)
    check("Dùng lại OTP đã sử dụng", s, 409, d)

    s, d = call("GET", f"{PAYMENT}/payments", token=phuc)
    check("Xem lịch sử giao dịch", s, 200)
    for g in d:
        print(f"     {g['MaGiaoDich'][:16]}… {g['MSSV']} {g['SoTienGiaoDich']:>12,.0f} {g['TrangThai']}")

    time.sleep(1)
    subjects = [m["Subject"] for m in call("GET", f"{MAILPIT}/search?query={txn}")[1]["messages"]]
    check_true(f"Email OTP + email xác nhận đã được gửi: {subjects}", len(subjects) == 2)


def scenario_concurrency1():
    print("=== Concurrency #1: phuc123 (15.5tr) đồng thời thanh toán 524K0011 (750k) + 523V0005 (15tr) ===")
    phuc = login("phuc123")
    t1 = create_payment(phuc, tuition_id(phuc, "524K0011"))[1]["transaction_id"]
    t2 = create_payment(phuc, tuition_id(phuc, "523V0005"))[1]["transaction_id"]
    o1, o2 = otp_from_mailpit(t1), otp_from_mailpit(t2)
    before = balance(phuc)

    results = run_concurrently(lambda: confirm(phuc, t1, o1), lambda: confirm(phuc, t2, o2))
    for (s, d), label in zip(results, ["524K0011", "523V0005"]):
        print(f"  {label}: HTTP {s} {d.get('detail') or d.get('message')}")

    after = balance(phuc)
    successes = sum(1 for s, _ in results if s == 200)
    print(f"  Số dư: {before:,.0f} -> {after:,.0f}")
    check_true("Chỉ 1 giao dịch thành công, số dư không âm", successes == 1 and after >= 0)


def scenario_concurrency2():
    print("=== Concurrency #2: khiem123 và nhi123 cùng lúc thanh toán 524K0011 (750k) ===")
    khiem, nhi = login("khiem123"), login("nhi123")
    hp = tuition_id(khiem, "524K0011")
    tk = create_payment(khiem, hp)[1]["transaction_id"]
    tn = create_payment(nhi, hp)[1]["transaction_id"]
    ok, on = otp_from_mailpit(tk), otp_from_mailpit(tn)
    before = {"khiem123": balance(khiem), "nhi123": balance(nhi)}

    results = run_concurrently(lambda: confirm(khiem, tk, ok), lambda: confirm(nhi, tn, on))
    for (s, d), label in zip(results, ["khiem123", "nhi123"]):
        print(f"  {label}: HTTP {s} {d.get('detail') or d.get('message')}")

    after = {"khiem123": balance(khiem), "nhi123": balance(nhi)}
    for user in before:
        print(f"  Số dư {user}: {before[user]:,.0f} -> {after[user]:,.0f}")
    statuses = sorted(s for s, _ in results)
    check_true("1 người thành công (200), người còn lại bị từ chối (409)", statuses == [200, 409])


GATEWAY_ROOT = GATEWAY.rsplit("/api/v1", 1)[0]          # http://localhost
GATEWAY_BLOCKED = {"detail": "Không tìm thấy API"}       # body 404 do chính Gateway trả về
DOCS = {"Auth Service": "auth", "Tuition Service": "tuitions", "Payment Service": "payments"}


def http_get(url):
    try:
        with urllib.request.urlopen(url, timeout=30) as res:
            return res.status, res.read().decode("utf-8")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8")


def scenario_gateway():
    """
    Đọc tài liệu Swagger (openapi.json) của từng service qua Gateway, rồi gọi thử MỌI API trong đó
    (không kèm token, không gây thay đổi dữ liệu):
      - API công khai phải đi tới được service: nhận 400/401 do service trả, không bị Gateway chặn
      - API nội bộ (tag chứa "Internal") phải bị Gateway chặn bằng 404
    """
    print("=== Swagger qua Gateway & định tuyến của Gateway ===")
    s, html = http_get(f"{GATEWAY_ROOT}/")
    check_true(f"Trang chủ {GATEWAY_ROOT}/ hiện trang đăng nhập (HTTP {s})", s == 200 and "login-form" in html)

    for title, prefix in DOCS.items():
        s, html = http_get(f"{GATEWAY}/{prefix}/docs")
        check_true(f"Swagger UI {GATEWAY}/{prefix}/docs (HTTP {s})", s == 200 and "swagger-ui" in html)
        s, spec = http_get(f"{GATEWAY}/{prefix}/openapi.json")
        spec = json.loads(spec)
        check_true(f"openapi.json là của {title}", s == 200 and spec["info"]["title"] == title)

        for path, methods in spec["paths"].items():
            url = GATEWAY_ROOT + re.sub(r"\{[^}]+\}", "1", path)
            for method, op in methods.items():
                internal = any("Internal" in tag for tag in op.get("tags", []))
                body = {} if method in ("post", "put", "patch") else None
                status, data = call(method.upper(), url, body)
                blocked = status == 404 and data == GATEWAY_BLOCKED
                if internal:
                    check_true(f"[nội bộ]    {method.upper():<4} {path} -> Gateway chặn (HTTP {status})", blocked)
                else:
                    check_true(f"[công khai] {method.upper():<4} {path} -> tới được service (HTTP {status})",
                               not blocked and status in (400, 401))

    s, _ = call("GET", f"{GATEWAY}/khong-ton-tai")
    check("API không tồn tại", s, 404)


if __name__ == "__main__":
    scenarios = {"api": scenario_api, "concurrency1": scenario_concurrency1, "concurrency2": scenario_concurrency2,
                 "gateway": scenario_gateway}
    name = sys.argv[1] if len(sys.argv) > 1 else "api"
    if name not in scenarios:
        sys.exit(f"Kịch bản hợp lệ: {', '.join(scenarios)}")
    scenarios[name]()
    print("\nKẾT QUẢ:", "TẤT CẢ ĐỀU ĐẠT" if failures == 0 else f"{failures} kiểm tra KHÔNG đạt")
    sys.exit(1 if failures else 0)
