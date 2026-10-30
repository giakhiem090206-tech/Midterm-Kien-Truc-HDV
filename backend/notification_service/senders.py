"""
Lớp Adapter cho các kênh gửi thông báo.

Mỗi nhà cung cấp/kênh gửi là một class cài đặt cùng interface NotificationSender.
Các service khác chỉ gọi REST API của Notification Service, không biết phía sau là
Gmail, Mailpit hay kênh nào. Muốn thêm kênh mới (Zalo, SMS...) chỉ cần viết thêm một
class và đăng ký trong build_senders(), không phải sửa Payment Service.
"""
import os
import smtplib
from abc import ABC, abstractmethod
from email.message import EmailMessage


class NotificationSender(ABC):
    """Interface chung của mọi adapter gửi thông báo"""

    @abstractmethod
    def send(self, to: str, subject: str, html: str) -> None:
        """Gửi thông báo, ném exception nếu gửi thất bại"""


class SmtpEmailSender(NotificationSender):
    """Gửi email qua SMTP: Mailpit khi chạy local (mặc định) hoặc Gmail (cấu hình trong .env)"""

    def __init__(self):
        self.host = os.getenv("SMTP_HOST", "mailpit")
        self.port = int(os.getenv("SMTP_PORT", "1025"))
        self.user = os.getenv("SMTP_USER", "")
        self.password = os.getenv("SMTP_PASSWORD", "").replace(" ", "")
        self.use_tls = os.getenv("SMTP_USE_TLS", "false").lower() == "true"
        self.mail_from = os.getenv("MAIL_FROM", "iBanking TDTU <no-reply@ibanking.local>")

    def send(self, to: str, subject: str, html: str) -> None:
        msg = EmailMessage()
        msg["From"] = self.mail_from
        msg["To"] = to
        msg["Subject"] = subject
        msg.set_content("Vui lòng mở email bằng trình đọc hỗ trợ HTML.")
        msg.add_alternative(html, subtype="html")

        with smtplib.SMTP(self.host, self.port, timeout=15) as smtp:
            if self.use_tls:
                smtp.starttls()
            if self.user:
                smtp.login(self.user, self.password)
            smtp.send_message(msg)


class ConsoleSender(NotificationSender):
    """Chỉ in thông báo ra log, dùng khi không có máy chủ mail (EMAIL_PROVIDER=console)"""

    def send(self, to: str, subject: str, html: str) -> None:
        print(f"[CONSOLE] Gửi tới {to} | {subject}\n{html}")


def build_senders() -> dict:
    """Đăng ký adapter cho từng kênh, chọn nhà cung cấp theo biến môi trường"""
    email_providers = {"smtp": SmtpEmailSender, "console": ConsoleSender}
    provider = os.getenv("EMAIL_PROVIDER", "smtp")
    if provider not in email_providers:
        raise ValueError(f"EMAIL_PROVIDER không hợp lệ: {provider}")
    return {
        "email": email_providers[provider](),
        # "zalo": ZaloSender(),  <- ví dụ: thêm kênh mới chỉ cần đăng ký ở đây
    }
