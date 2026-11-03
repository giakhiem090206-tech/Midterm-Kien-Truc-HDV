import os
import smtplib
from abc import ABC, abstractmethod
from email.message import EmailMessage
from email.utils import parseaddr

class NotificationSender(ABC):
    @abstractmethod
    def send(self, to: str, subject: str, html: str) -> None:
        pass

class SmtpEmailSender(NotificationSender):
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
            raise RuntimeError("Cần cấu hình SMTP_USER và Mật khẩu ứng dụng SMTP_PASSWORD trong .env")

        from_address = parseaddr(self.mail_from)[1]
        if self.host == "smtp.gmail.com" and self.user.casefold() != from_address.casefold():
            raise RuntimeError("Với Gmail SMTP, MAIL_FROM phải khớp SMTP_USER")

        msg = EmailMessage()
        msg["From"] = self.mail_from
        msg["To"] = recipient
        msg["Subject"] = subject
        msg.set_content("Vui lòng mở email bằng trình đọc hỗ trợ HTML.")
        msg.add_alternative(html, subtype="html")

        try:
            with smtplib.SMTP(self.host, self.port, timeout=15) as smtp:
                if self.use_tls:
                    smtp.starttls()
                if self.user:
                    smtp.login(self.user, self.password)
                smtp.send_message(msg)
                print(f"[SUCCESS] Đã gửi email tới {recipient}")
        except (smtplib.SMTPException, OSError) as e:
            raise RuntimeError(f"SMTP không gửi được email tới {recipient}") from e

class ConsoleSender(NotificationSender):
    def send(self, to: str, subject: str, html: str) -> None:
        print(f"[CONSOLE] Gửi tới {to} | {subject}\n{html}")

def build_senders() -> dict:
    providers = {"smtp": SmtpEmailSender, "console": ConsoleSender}
    provider = os.getenv("EMAIL_PROVIDER", "smtp")
    if provider not in providers:
        raise ValueError(f"EMAIL_PROVIDER không hợp lệ: {provider}")
    return {"email": providers[provider]()}

# Khởi tạo instance để các service khác import
notification_service = build_senders()["email"]

# Hàm tiện ích tương thích với luồng gọi cũ
def send_otp_email(to_email: str, otp_code: str):
    html_content = f"<h3>TDTU iBanking</h3><p>Mã OTP của bạn là: <b>{otp_code}</b>. Có hiệu lực trong 5 phút.</p>"
    notification_service.send(to_email, "[TDTU iBanking] Mã xác thực OTP", html_content)