"""Send a clearly labeled SMTP test OTP to every account in auth_db."""

import json
from pathlib import Path
import secrets
import subprocess
import sys
import uuid

sys.stdout.reconfigure(encoding="utf-8")
sys.stderr.reconfigure(encoding="utf-8")


ROOT = Path(__file__).resolve().parent
DATABASE_QUERY = """
SELECT COALESCE(
    json_agg(
        json_build_object(
            'username', "TenDangNhap",
            'full_name', "HoTen",
            'email', "Email"
        ) ORDER BY "MaNguoiDung"
    ),
    '[]'::json
)
FROM "NguoiDung";
"""
SEND_NOTIFICATION = """
import json
import os
import sys
from urllib.request import Request, urlopen

payload = json.load(sys.stdin)
request = Request(
    'http://127.0.0.1:8004/api/v1/notifications',
    data=json.dumps(payload).encode('utf-8'),
    headers={
        'Content-Type': 'application/json',
        'X-Internal-Key': os.environ['INTERNAL_API_KEY'],
    },
    method='POST',
)
with urlopen(request, timeout=30) as response:
    print(response.read().decode('utf-8'))
"""


def compose(*args: str, input_text: str | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["docker", "compose", *args],
        cwd=ROOT,
        input=input_text,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=True,
    )


def main() -> int:
    if len(sys.argv) > 1:
        print("Usage: python test_concurrency.py")
        return 2

    try:
        accounts = json.loads(
            compose(
                "exec", "-T", "db", "psql", "-U", "root", "-d", "auth_db",
                "-At", "-v", "ON_ERROR_STOP=1", "-c", DATABASE_QUERY,
            ).stdout
        )
    except (subprocess.CalledProcessError, json.JSONDecodeError) as error:
        print(f"Không đọc được danh sách tài khoản trong auth_db: {error}", file=sys.stderr)
        return 1

    if not accounts:
        print("auth_db không có tài khoản nào để kiểm tra.", file=sys.stderr)
        return 1

    sent = 0
    skipped = 0
    failed = 0
    for account in accounts:
        email = (account.get("email") or "").strip()
        if not email.casefold().endswith("@student.tdtu.edu.vn"):
            print(f"Bỏ qua {account['username']}: email không thuộc miền sinh viên TDTU.")
            skipped += 1
            continue

        payload = {
            "channel": "email",
            "to": email,
            "template": "OTP_TEST",
            "data": {
                "full_name": account["full_name"],
                "otp": f"{secrets.randbelow(1_000_000):06d}",
                "transaction_id": f"SMTP-TEST-{uuid.uuid4().hex[:12]}",
            },
        }
        try:
            response = json.loads(
                compose(
                    "exec", "-T", "notification-service", "python", "-c",
                    SEND_NOTIFICATION,
                    input_text=json.dumps(payload, ensure_ascii=False),
                ).stdout
            )
        except (subprocess.CalledProcessError, json.JSONDecodeError) as error:
            print(f"❌ Gửi email kiểm thử tới {email} thất bại: {error}")
            failed += 1
            continue

        if response.get("status") == "SENT" and response.get("to") == email:
            print(f"✅ Notification Service đã gửi email kiểm thử tới {email}.")
            sent += 1
        else:
            print(f"❌ Phản hồi gửi email kiểm thử không hợp lệ cho {email}: {response}")
            failed += 1

    print(f"Hoàn tất: gửi thành công {sent}, bỏ qua {skipped}, thất bại {failed}.")
    print("Kiểm tra Inbox/Spam để xác nhận email thực sự đã tới.")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
