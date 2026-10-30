"""Integration checks for idempotency and automatic payment-saga recovery.

Run against a fresh `docker compose up -d --build` stack. The recovery test
temporarily stops tuition-service and always starts it again in a finally block.
"""
import json
import os
import subprocess
import time
import unittest
import urllib.error
import urllib.parse
import urllib.request


# Mọi API đi qua API Gateway; stack kiểm thử dùng DEMO_GATEWAY_URL=http://localhost:18080/api/v1
GATEWAY = os.getenv("DEMO_GATEWAY_URL", "http://localhost/api/v1")
AUTH = TUITION = PAYMENT = GATEWAY
MAILPIT = os.getenv("DEMO_MAILPIT_URL", "http://localhost:8025/api/v1")
COMPOSE_FILES = os.getenv("TEST_COMPOSE_FILES", "").split(";")
COMPOSE_PROJECT = os.getenv("TEST_COMPOSE_PROJECT", "")


def compose(*args):
    command = ["docker", "compose"]
    for path in filter(None, COMPOSE_FILES):
        command.extend(["-f", path])
    if COMPOSE_PROJECT:
        command.extend(["-p", COMPOSE_PROJECT])
    subprocess.run(command + list(args), check=True, capture_output=True, text=True)


def request(method, url, body=None, token=None):
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=20) as response:
            return response.status, json.loads(response.read() or "null")
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read() or "null")


def login(username):
    code, result = request("POST", f"{AUTH}/auth/login", {
        "username": username, "password": "123456"
    })
    if code != 200:
        raise AssertionError(f"Login failed: HTTP {code} {result}")
    return result["access_token"]


def read_otp(transaction_id):
    query = urllib.parse.quote(transaction_id)
    for _ in range(40):
        _, result = request("GET", f"{MAILPIT}/search?query={query}")
        for message in result.get("messages", []):
            _, body = request("GET", f"{MAILPIT}/message/{message['ID']}")
            import re
            match = re.search(r'letter-spacing: 8px;">(\d{6})<', body.get("HTML", ""))
            if match:
                return match.group(1)
        time.sleep(0.25)
    raise AssertionError("OTP email was not found in Mailpit")


class SagaRecoveryTests(unittest.TestCase):
    def test_processing_payment_recovers_after_tuition_restart(self):
        token = login("phuc123")
        _, before_profile = request("GET", f"{AUTH}/users/me", token=token)
        before_balance = before_profile["available_balance"]
        code, tuition = request("GET", f"{TUITION}/tuitions/524K0011", token=token)
        self.assertEqual(code, 200, tuition)
        _, created = request("POST", f"{PAYMENT}/payments", {
            "MaHocPhi": tuition["MaHocPhi"]
        }, token=token)
        transaction_id = created["transaction_id"]
        otp = read_otp(transaction_id)

        compose("stop", "tuition-service")
        try:
            code, _ = request("POST", f"{PAYMENT}/payments/{transaction_id}/confirm", {
                "otp": otp
            }, token=token)
            self.assertEqual(code, 503, "Tuition outage should leave a retryable saga")
            code, detail = request("GET", f"{PAYMENT}/payments/{transaction_id}", token=token)
            self.assertEqual(code, 200, detail)
            self.assertEqual(detail["TrangThai"], "PROCESSING")
        finally:
            compose("start", "tuition-service")

        deadline = time.time() + 60
        while time.time() < deadline:
            code, detail = request("GET", f"{PAYMENT}/payments/{transaction_id}", token=token)
            if code == 200 and detail["TrangThai"] in ("SUCCESS", "FAILED"):
                break
            time.sleep(2)
        self.assertEqual(detail["TrangThai"], "SUCCESS", detail)
        _, after_profile = request("GET", f"{AUTH}/users/me", token=token)
        self.assertEqual(
            after_profile["available_balance"],
            before_balance - tuition["SoTienPhaiNop"],
            "Recovery must not debit the same transaction more than once"
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
