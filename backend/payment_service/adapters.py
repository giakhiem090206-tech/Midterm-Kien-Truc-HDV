"""
ADAPTER PATTERN CHO DỊCH VỤ NGOÀI (EXTERNAL SERVICES)
Áp dụng thiết kế: BE App -> Adapter Interface -> Concrete Adapters (Gmail SMTP / Console / Zalo...)
Giúp tách biệt hoàn toàn logic nghiệp vụ của Payment Service khỏi chi tiết kỹ thuật của nhà cung cấp dịch vụ bên ngoài.
"""

import os
import smtplib
from abc import ABC, abstractmethod
from email.message import EmailMessage
from typing import Optional


class NotificationAdapter(ABC):
    """Interface chuẩn (Target Interface) cho mọi kênh gửi thông báo ra bên ngoài."""

    @abstractmethod
    def send(self, recipient: str, subject: str, text_body: str, html_body: Optional[str] = None) -> bool:
        pass


class GmailSMTPAdapter(NotificationAdapter):
    """Concrete Adapter kết nối tới dịch vụ Gmail SMTP bên ngoài."""

    def __init__(self, host: str, port: int, user: str, password: str):
        self.host = host
        self.port = port
        self.user = user
        self.password = password.replace(" ", "").strip()

    def send(self, recipient: str, subject: str, text_body: str, html_body: Optional[str] = None) -> bool:
        print("\n" + "=" * 65)
        print(f"[ADAPTER: GmailSMTPAdapter] To: {recipient} | From: {self.user}")
        print(f"[ADAPTER: GmailSMTPAdapter] Subject: {subject}")
        print("-" * 65)
        print(text_body)
        print("=" * 65 + "\n")

        try:
            msg = EmailMessage()
            msg["Subject"] = subject
            msg["From"] = f"TDTU iBanking <{self.user}>"
            msg["To"] = recipient
            msg.set_content(text_body)
            if html_body:
                msg.add_alternative(html_body, subtype="html")

            with smtplib.SMTP(self.host, self.port, timeout=15) as server:
                server.ehlo()
                server.starttls()
                server.ehlo()
                server.login(self.user, self.password)
                server.send_message(msg)
            print(f"[ADAPTER SUCCESS] Đã gửi email thật tới {recipient} qua GmailSMTPAdapter!")
            return True
        except Exception as e:
            print(f"[ADAPTER ERROR] GmailSMTPAdapter gặp lỗi: {e}")
            return False


class ConsoleMailAdapter(NotificationAdapter):
    """Concrete Adapter dự phòng (Fallback) khi chạy môi trường offline không có mạng SMTP."""

    def send(self, recipient: str, subject: str, text_body: str, html_body: Optional[str] = None) -> bool:
        print("\n" + "=" * 65)
        print(f"[ADAPTER: ConsoleMailAdapter] To: {recipient}")
        print(f"[ADAPTER: ConsoleMailAdapter] Subject: {subject}")
        print("-" * 65)
        print(text_body)
        print("=" * 65 + "\n")
        return False


def get_notification_adapter() -> NotificationAdapter:
    """
    Factory khởi tạo Adapter dựa trên Config môi trường (Config-driven Adapter).
    Nếu đổi nhà cung cấp từ Gmail sang MailX / SendGrid / Zalo, chỉ cần thay đổi tại Adapter này
    mà không phải sửa code nghiệp vụ của Payment Service.
    """
    smtp_host = (os.getenv("SMTP_HOST") or "smtp.gmail.com").strip()
    smtp_port = int((os.getenv("SMTP_PORT") or "587").strip())
    smtp_user = (os.getenv("SMTP_USER") or "giaphucnguyen36573@gmail.com").strip()
    if "nhap_gmail" in smtp_user or not smtp_user:
        smtp_user = "giaphucnguyen36573@gmail.com"

    raw_pass = (os.getenv("SMTP_PASSWORD") or "perm vvkd sjxv msqr").replace(" ", "").strip()
    if "xxxx" in raw_pass or not raw_pass:
        raw_pass = "permvvkdsjxvmsqr"

    if smtp_host and smtp_user and raw_pass:
        return GmailSMTPAdapter(host=smtp_host, port=smtp_port, user=smtp_user, password=raw_pass)
    return ConsoleMailAdapter()

