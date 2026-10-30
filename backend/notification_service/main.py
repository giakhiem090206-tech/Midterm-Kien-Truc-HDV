from datetime import datetime, timedelta, timezone
from html import escape
from typing import Literal
from fastapi import Depends, HTTPException, status
from pydantic import BaseModel, Field
from security import verify_internal_key
from senders import build_senders
from service_app import create_app

# 1. Cấu hình
VN_TZ = timezone(timedelta(hours=7))

# Adapter cho từng kênh gửi (xem senders.py)
SENDERS = build_senders()

# 2. Khởi tạo FastAPI
# Service nội bộ: API Gateway không mở ra ngoài, Swagger chỉ xem được khi chạy docker-compose.dev.yml
app, logger = create_app("Notification Service", "notification-service")

# 3. Mẫu nội dung thông báo
def _format_vnd(amount) -> str:
    return f"{float(amount):,.0f}".replace(",", ".") + " VNĐ"

def _render_otp(data: dict) -> tuple:
    return (
        "[iBanking TDTU] Mã OTP xác nhận thanh toán học phí",
        f"""
        <h2>Mã OTP xác nhận giao dịch</h2>
        <p>Xin chào <b>{escape(data['full_name'])}</b>,</p>
        <p>Bạn đang thanh toán học phí cho sinh viên
           <b>{escape(data['mssv'])} - {escape(data['student_name'])}</b>
           với số tiền <b>{_format_vnd(data['amount'])}</b>.</p>
        <p>Mã OTP của bạn là:</p>
        <p style="font-size: 32px; font-weight: bold; letter-spacing: 8px;">{escape(data['otp'])}</p>
        <p>Mã có hiệu lực trong <b>{int(data['ttl_minutes'])} phút</b> và chỉ được sử dụng một lần.
           Không chia sẻ mã này cho bất kỳ ai.</p>
        <p style="color: #888;">Mã giao dịch: {escape(data['transaction_id'])}</p>
        """
    )

def _render_payment_success(data: dict) -> tuple:
    return (
        "[iBanking TDTU] Thanh toán học phí thành công",
        f"""
        <h2>Thanh toán học phí thành công</h2>
        <p>Xin chào <b>{escape(data['full_name'])}</b>,</p>
        <p>Giao dịch thanh toán học phí của bạn đã được thực hiện thành công.</p>
        <table cellpadding="6">
            <tr><td>Mã giao dịch:</td><td><b>{escape(data['transaction_id'])}</b></td></tr>
            <tr><td>Sinh viên:</td><td>{escape(data['mssv'])} - {escape(data['student_name'])}</td></tr>
            <tr><td>Số tiền:</td><td><b>{_format_vnd(data['amount'])}</b></td></tr>
            <tr><td>Số dư còn lại:</td><td>{_format_vnd(data['new_balance'])}</td></tr>
            <tr><td>Thời gian:</td><td>{datetime.now(VN_TZ).strftime('%H:%M:%S %d/%m/%Y')}</td></tr>
        </table>
        """
    )

TEMPLATES = {
    "OTP": _render_otp,
    "PAYMENT_SUCCESS": _render_payment_success,
}

# 4. Pydantic Schemas
class NotificationRequest(BaseModel):
    channel: str = "email"
    to: str = Field(min_length=3, max_length=100)
    template: Literal["OTP", "PAYMENT_SUCCESS"]
    data: dict

class NotificationResponse(BaseModel):
    status: str
    channel: str
    to: str

# 5. API Endpoints

@app.post("/api/v1/notifications", response_model=NotificationResponse, status_code=status.HTTP_201_CREATED,
          tags=["Notification Internal"], dependencies=[Depends(verify_internal_key)])
def send_notification(request: NotificationRequest):
    """
    API nội bộ: dựng nội dung theo mẫu (template) rồi giao cho adapter của kênh tương ứng gửi đi
    """
    sender = SENDERS.get(request.channel)
    if not sender:
        raise HTTPException(status_code=400, detail=f"Kênh thông báo không được hỗ trợ: {request.channel}")

    try:
        subject, html = TEMPLATES[request.template](request.data)
    except (KeyError, TypeError, ValueError) as e:
        raise HTTPException(status_code=400, detail=f"Thiếu hoặc sai dữ liệu cho mẫu {request.template}: {e}")

    try:
        sender.send(request.to, subject, html)
    except Exception as e:
        logger.error("Không gửi được %s tới %s: %s", request.template, request.to, e)
        raise HTTPException(status_code=502, detail="Không gửi được thông báo")

    return {"status": "SENT", "channel": request.channel, "to": request.to}
