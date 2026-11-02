"""
Lớp Adapter cho các kênh gửi thông báo.

Mỗi nhà cung cấp/kênh gửi là một class cài đặt cùng interface NotificationSender.
Các service khác chỉ gọi REST API của Notification Service, không biết phía sau là
SMTP server hay kênh nào. Muốn thêm kênh mới (Zalo, SMS...) chỉ cần viết thêm một
class và đăng ký trong build_senders(), không phải sửa Payment Service.
"""
import os
import smtplib
from abc import ABC, abstractmethod
from email.message import EmailMessage
from email.utils import parseaddr


class NotificationSender(ABC):
    """Interface chung của mọi adapter gửi thông báo"""

    @abstractmethod
    def send(self, to: str, subject: str, html: str) -> None:
        """Gửi thông báo, ném exception nếu gửi thất bại"""


class SmtpEmailSender(NotificationSender):
    """Gửi email qua SMTP với cấu hình lấy từ môi trường."""

    def __init__(self):
        self.host = os.getenv("SMTP_HOST", "smtp.gmail.com")
        self.port = int(os.getenv("SMTP_PORT", "587"))
        self.user = os.getenv("SMTP_USER", "")
        self.password = os.getenv("SMTP_PASSWORD", "").replace(" ", "")
        tls_setting = os.getenv("SMTP_USE_TLS", "").lower()
        self.use_tls = tls_setting == "true" if tls_setting else True
        self.mail_from = os.getenv("MAIL_FROM", "").strip() or self.user

    def send(self, to: str, subject: str, html: str) -> None:
        recipient = to.strip()
        if not recipient.casefold().endswith("@student.tdtu.edu.vn"):
            raise ValueError("Chỉ gửi OTP và thông báo tới email @student.tdtu.edu.vn")
        if self.host == "smtp.gmail.com" and (not self.user or not self.password):
            raise RuntimeError("Cần cấu hình SMTP_USER và App Password SMTP_PASSWORD trong .env để gửi email Gmail")
        from_address = parseaddr(self.mail_from)[1]
        if self.host == "smtp.gmail.com" and self.user.casefold() != from_address.casefold():
            raise RuntimeError(
                "Với Gmail SMTP, địa chỉ trong MAIL_FROM phải khớp SMTP_USER; "
                "có thể đặt tên hiển thị như 'iBanking TDTU <email@gmail.com>'"
            )

        msg = EmailMessage()
        msg["From"] = self.mail_from
        msg["To"] = recipient
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
