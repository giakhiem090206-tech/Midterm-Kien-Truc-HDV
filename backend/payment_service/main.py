import os
import random
import smtplib
from email.message import EmailMessage
from datetime import datetime, timedelta
from typing import Optional, Dict, Any
import httpx
from fastapi import FastAPI, Depends, HTTPException, status, Header
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from sqlalchemy import Column, Integer, String, Numeric, DateTime, create_engine
from sqlalchemy.orm import declarative_base, Session, sessionmaker
from adapters import get_notification_adapter

# 1. Cấu hình Database & Endpoint của các Microservices khác
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://root:rootpassword@db:5432/ibanking")
AUTH_SERVICE_URL = os.getenv("AUTH_SERVICE_URL", "http://auth-service:8001")
TUITION_SERVICE_URL = os.getenv("TUITION_SERVICE_URL", "http://tuition-service:8002")

# Cấu hình SMTP Email (mặc định smtp.gmail.com:587; sử dụng tài khoản Gmail & App Password đã cấu hình)
SMTP_HOST = os.getenv("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER = os.getenv("SMTP_USER", "giaphucnguyen36573@gmail.com")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "perm vvkd sjxv msqr")

engine = create_engine(DATABASE_URL, pool_pre_ping=True)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# 2. Database Models (đồng bộ 100% với init.sql)
class GiaoDichModel(Base):
    __tablename__ = "giao_dich"
    ma_giao_dich = Column(String(50), primary_key=True)
    ma_nguoi_dung = Column(Integer, nullable=False)
    ma_hoc_phi = Column(Integer, nullable=False)
    so_tien_giao_dich = Column(Numeric(15, 2), nullable=False)
    thoi_gian_tao = Column(DateTime, nullable=False, default=datetime.utcnow)
    trang_thai = Column(String(30), nullable=False)  # 'PENDING', 'SUCCESS', 'FAILED'

class XacThucOTPModel(Base):
    __tablename__ = "xac_thuc_otp"
    ma_otp = Column(Integer, primary_key=True, index=True)
    ma_giao_dich = Column(String(50), nullable=False, index=True)
    ma_code = Column(String(10), nullable=False)
    thoi_gian_tao = Column(DateTime, nullable=False, default=datetime.utcnow)
    thoi_gian_het_han = Column(DateTime, nullable=False)
    trang_thai = Column(String(30), nullable=False)  # 'CHUA_SU_DUNG', 'DA_SU_DUNG', 'HET_HAN'

class UserModel(Base):
    __tablename__ = "nguoi_dung"
    ma_nguoi_dung = Column(Integer, primary_key=True)
    mssv = Column(String(20), nullable=False)
    ten_dang_nhap = Column(String(50), nullable=False)
    ho_ten = Column(String(100), nullable=False)
    so_dien_thoai = Column(String(20), nullable=False)
    email = Column(String(100), nullable=False)
    so_du = Column(Numeric(15, 2), nullable=False)

class HocPhiModel(Base):
    __tablename__ = "hoc_phi"
    ma_hoc_phi = Column(Integer, primary_key=True)
    mssv = Column(String(20), nullable=False)
    ho_ten_sinh_vien = Column(String(100), nullable=False)
    hoc_ky = Column(String(50), nullable=False)
    so_tien_phai_nop = Column(Numeric(15, 2), nullable=False)
    trang_thai = Column(String(30), nullable=False)

Base.metadata.create_all(bind=engine)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# Bộ nhớ lưu trữ Idempotency-Key (IK) chống xử lý trùng lặp khi mạng retry / người dùng bấm đúp
IDEMPOTENCY_STORE: Dict[str, Dict[str, Any]] = {}

def send_email_notification(to_email: str, subject: str, body_text: str, html_body: Optional[str] = None) -> bool:
    """
    Gửi thông báo qua tầng Adapter (NotificationAdapter -> GmailSMTPAdapter / ConsoleMailAdapter).
    """
    adapter = get_notification_adapter()
    return adapter.send(recipient=to_email, subject=subject, text_body=body_text, html_body=html_body)

# 3. Khởi tạo FastAPI & CORS
app = FastAPI(
    title="Payment Service - TDTU iBanking",
    description="Microservice điều phối thanh toán học phí, sinh/xác thực OTP, xử lý Transaction & Concurrency",
    version="1.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 4. Pydantic Schemas
class InitiatePaymentRequest(BaseModel):
    MaNguoiDung: int = Field(..., gt=0, description="Mã người dùng nộp tiền")
    MaHocPhi: int = Field(..., gt=0, description="Mã khoản học phí cần thanh toán")
    email: Optional[str] = Field(default=None, description="Địa chỉ Gmail người dùng nhập để nhận OTP")

class InitiatePaymentResponse(BaseModel):
    transaction_id: str
    MaGiaoDich: str
    email: str
    smtp_sent: bool = False
    expires_in_seconds: int = 300
    otp_demo: str
    idempotency_key: Optional[str] = None
    idempotent_replay: bool = False
    message: str

class ConfirmPaymentRequest(BaseModel):
    MaGiaoDich: str = Field(..., min_length=1, description="Mã giao dịch cần xác nhận")
    otp: str = Field(..., min_length=1, description="Mã OTP 6 chữ số")
    email: Optional[str] = Field(default=None, description="Địa chỉ Gmail nhận biên lai xác nhận")

class TransactionResponse(BaseModel):
    message: str
    transaction_id: str
    MaGiaoDich: str
    status: str
    amount: Optional[float] = None
    new_balance: Optional[float] = None
    mssv: Optional[str] = None
    student_name: Optional[str] = None
    semester: Optional[str] = None
    email_sent_to: Optional[str] = None
    idempotency_key: Optional[str] = None
    idempotent_replay: bool = False

class WebhookCallbackRequest(BaseModel):
    MaGiaoDich: str
    event_type: str = "PAYMENT_CONFIRMED"
    status: str = "SUCCESS"

# 5. API Endpoints

@app.post(
    "/api/v1/payments/initiate",
    response_model=InitiatePaymentResponse,
    status_code=status.HTTP_201_CREATED,
    tags=["Payment"]
)
async def initiate_payment(
    request: InitiatePaymentRequest,
    idempotency_key: Optional[str] = Header(default=None, alias="Idempotency-Key"),
    db: Session = Depends(get_db)
):
    """
    Bước 1: Khởi tạo giao dịch thanh toán học phí (Hỗ trợ Idempotency-Key chống tạo giao dịch trùng).
    - Giao tiếp với Auth Service kiểm tra thông tin người nộp & số dư khả dụng.
    - Giao tiếp với Tuition Service kiểm tra khoản học phí tồn tại và chưa được thanh toán.
    - Sinh mã OTP 6 chữ số (gắn với giao dịch, không trùng với OTP đang có hiệu lực, hạn 5 phút, dùng 1 lần).
    - Gửi mã OTP qua Adapter tới địa chỉ email.
    """
    if idempotency_key:
        ik_cache_key = f"INITIATE:{idempotency_key.strip()}"
        if ik_cache_key in IDEMPOTENCY_STORE:
            cached_resp = dict(IDEMPOTENCY_STORE[ik_cache_key])
            cached_resp["idempotent_replay"] = True
            return cached_resp
    async with httpx.AsyncClient(timeout=10.0) as client:
        # Gọi Auth Service lấy thông tin người dùng & số dư
        user_res = await client.get(f"{AUTH_SERVICE_URL}/api/v1/users/{request.MaNguoiDung}")
        if user_res.status_code == 404:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Không tìm thấy người dùng nộp tiền")
        if user_res.status_code != 200:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Người dùng không hợp lệ")
        user_data = user_res.json()

        # Gọi Tuition Service lấy thông tin khoản học phí
        tuition_res = await client.get(f"{TUITION_SERVICE_URL}/api/v1/tuitions/detail/{request.MaHocPhi}")
        if tuition_res.status_code == 404:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Khoản học phí không tồn tại")
        if tuition_res.status_code != 200:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Khoản học phí không hợp lệ")
        tuition_data = tuition_res.json()

    # Kiểm tra trạng thái học phí phải chưa được thanh toán
    if tuition_data.get("TrangThai") == "DA_DONG":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Khoản học phí này đã được thanh toán!"
        )

    # Kiểm tra số dư khả dụng >= số tiền cần thanh toán
    available_balance = float(user_data.get("available_balance", 0))
    tuition_amount = float(tuition_data.get("SoTienPhaiNop", 0))
    if available_balance < tuition_amount:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Số dư khả dụng không đủ để thực hiện giao dịch"
        )

    now = datetime.utcnow()
    # Sinh mã giao dịch duy nhất (kết hợp timestamp microsecond và số ngẫu nhiên để không trùng khi bắn Concurrency)
    ma_giao_dich = f"TXN_{now.strftime('%Y%m%d%H%M%S%f')}_{random.randint(100, 999)}"

    gd = GiaoDichModel(
        ma_giao_dich=ma_giao_dich,
        ma_nguoi_dung=request.MaNguoiDung,
        ma_hoc_phi=request.MaHocPhi,
        so_tien_giao_dich=tuition_amount,
        thoi_gian_tao=now,
        trang_thai="PENDING"
    )
    db.add(gd)

    # Sinh OTP 6 chữ số ngẫu nhiên, ĐẢM BẢO KHÔNG TRÙNG với bất kỳ OTP nào đang còn hiệu lực của giao dịch khác
    while True:
        ma_code = f"{random.randint(100000, 999999)}"
        duplicate_active_otp = (
            db.query(XacThucOTPModel)
            .filter(
                XacThucOTPModel.ma_code == ma_code,
                XacThucOTPModel.trang_thai == "CHUA_SU_DUNG",
                XacThucOTPModel.thoi_gian_het_han > now
            )
            .first()
        )
        if not duplicate_active_otp:
            break

    expires_at = now + timedelta(minutes=5)
    otp = XacThucOTPModel(
        ma_giao_dich=ma_giao_dich,
        ma_code=ma_code,
        thoi_gian_tao=now,
        thoi_gian_het_han=expires_at,
        trang_thai="CHUA_SU_DUNG"
    )
    db.add(otp)
    db.commit()

    # Email nhận OTP ưu tiên lấy từ địa chỉ Gmail người dùng tự nhập, nếu không có mới lấy email tài khoản
    target_email = (
        request.email.strip()
        if request.email and request.email.strip()
        else user_data.get("email", "unknown@student.tdtu.edu.vn")
    )
    if "@" not in target_email:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Địa chỉ Gmail nhận OTP không hợp lệ"
        )

    email_body = (
        f"Xin chào {user_data.get('full_name')},\n\n"
        f"Bạn vừa yêu cầu thanh toán học phí trên hệ thống TDTU iBanking:\n"
        f"- Mã giao dịch: {ma_giao_dich}\n"
        f"- Sinh viên thụ hưởng: {tuition_data.get('HoTen')} - MSSV: {tuition_data.get('MSSV')}\n"
        f"- Học kỳ: {tuition_data.get('HocKy')}\n"
        f"- Số tiền thanh toán: {tuition_amount:,.0f} VNĐ\n\n"
        f"Mã xác thực OTP của bạn là: {ma_code}\n"
        f"Mã OTP có hiệu lực trong vòng 05 phút và chỉ sử dụng 01 lần.\n\n"
        f"Trân trọng,\nTDTU iBanking System"
    )
    email_html = f"""
    <div style="font-family: Arial, sans-serif; max-width: 560px; margin: 0 auto; border: 1px solid #dce2ec; border-radius: 8px; overflow: hidden;">
        <div style="background-color: #0A3D91; color: white; padding: 16px 24px; font-size: 18px; font-weight: bold;">
            TDTU iBanking - Xác Thực Giao Dịch Đóng Học Phí
        </div>
        <div style="padding: 20px 24px; color: #333; line-height: 1.6;">
            <p>Xin chào <strong>{user_data.get('full_name')}</strong>,</p>
            <p>Hệ thống nhận được yêu cầu thanh toán học phí với thông tin chi tiết:</p>
            <table style="width: 100%; border-collapse: collapse; margin: 12px 0;">
                <tr><td style="padding: 6px 0; color: #555;">Mã giao dịch:</td><td style="padding: 6px 0; font-weight: bold;">{ma_giao_dich}</td></tr>
                <tr><td style="padding: 6px 0; color: #555;">Mã số sinh viên:</td><td style="padding: 6px 0; font-weight: bold;">{tuition_data.get('MSSV')}</td></tr>
                <tr><td style="padding: 6px 0; color: #555;">Họ và tên sinh viên:</td><td style="padding: 6px 0; font-weight: bold;">{tuition_data.get('HoTen')}</td></tr>
                <tr><td style="padding: 6px 0; color: #555;">Học kỳ:</td><td style="padding: 6px 0; font-weight: bold;">{tuition_data.get('HocKy')}</td></tr>
                <tr><td style="padding: 6px 0; color: #555;">Số tiền thanh toán:</td><td style="padding: 6px 0; font-weight: bold; color: #d9534f;">{tuition_amount:,.0f} VNĐ</td></tr>
            </table>
            <div style="text-align: center; margin: 20px 0; padding: 16px; background: #f4f7f9; border-radius: 8px;">
                <div style="font-size: 14px; color: #555; margin-bottom: 6px;">Mã xác thực OTP của bạn</div>
                <div style="font-size: 28px; font-weight: bold; letter-spacing: 6px; color: #0A3D91;">{ma_code}</div>
                <div style="font-size: 12px; color: #777; margin-top: 6px;">Hiệu lực tối đa 05 phút và chỉ sử dụng 01 lần</div>
            </div>
            <p style="font-size: 13px; color: #666;">Nếu bạn không thực hiện giao dịch này, vui lòng bỏ qua email này.</p>
        </div>
    </div>
    """
    smtp_sent = send_email_notification(
        to_email=target_email,
        subject=f"[TDTU iBanking] Mã xác thực OTP giao dịch {ma_giao_dich}",
        body_text=email_body,
        html_body=email_html
    )

    result_payload = {
        "transaction_id": ma_giao_dich,
        "MaGiaoDich": ma_giao_dich,
        "email": target_email,
        "smtp_sent": smtp_sent,
        "expires_in_seconds": 300,
        "otp_demo": ma_code,
        "idempotency_key": idempotency_key,
        "idempotent_replay": False,
        "message": f"Mã OTP đã được gửi đến địa chỉ {target_email}. Hiệu lực trong 5 phút."
    }
    if idempotency_key:
        IDEMPOTENCY_STORE[f"INITIATE:{idempotency_key.strip()}"] = result_payload
    return result_payload

@app.get("/api/v1/payments/qr/{transaction_id}", tags=["Payment"])
def get_payment_qr(transaction_id: str, db: Session = Depends(get_db)):
    """Trả về dữ liệu QR cho giao dịch đang chờ xác nhận."""
    gd = db.query(GiaoDichModel).filter(GiaoDichModel.ma_giao_dich == transaction_id).first()
    if not gd:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Không tìm thấy giao dịch")

    qr_data = f"IBANKING|{transaction_id}|{gd.ma_nguoi_dung}|{float(gd.so_tien_giao_dich)}|TDTU"
    return {
        "transaction_id": transaction_id,
        "amount": float(gd.so_tien_giao_dich),
        "merchant": "TDTU iBanking",
        "qr_data": qr_data
    }

@app.post("/api/v1/payments/confirm", response_model=TransactionResponse, tags=["Payment"])
async def confirm_payment(
    request: ConfirmPaymentRequest,
    idempotency_key: Optional[str] = Header(default=None, alias="Idempotency-Key"),
    db: Session = Depends(get_db)
):
    """
    Bước 2: Xác thực OTP và xử lý giao dịch thành công (Đảm bảo ACID, Concurrency & Idempotency-Key).
    """
    if idempotency_key:
        ik_cache_key = f"CONFIRM:{idempotency_key.strip()}"
        if ik_cache_key in IDEMPOTENCY_STORE:
            cached_resp = dict(IDEMPOTENCY_STORE[ik_cache_key])
            cached_resp["idempotent_replay"] = True
            return cached_resp

    now = datetime.utcnow()

    try:
        # 1. Khóa dòng giao dịch để kiểm tra trạng thái
        gd = (
            db.query(GiaoDichModel)
            .filter(GiaoDichModel.ma_giao_dich == request.MaGiaoDich)
            .with_for_update()
            .first()
        )
        if not gd:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Không tìm thấy giao dịch"
            )

        if gd.trang_thai == "SUCCESS":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Giao dịch này đã được thanh toán thành công trước đó"
            )

        if gd.trang_thai == "FAILED":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Giao dịch này đã kết thúc hoặc bị từ chối trước đó"
            )

        # 2. Khóa và kiểm tra mã OTP gắn với giao dịch
        otp_record = (
            db.query(XacThucOTPModel)
            .filter(
                XacThucOTPModel.ma_giao_dich == request.MaGiaoDich,
                XacThucOTPModel.ma_code == request.otp.strip()
            )
            .with_for_update()
            .first()
        )

        if not otp_record:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Mã OTP không chính xác"
            )

        if otp_record.trang_thai != "CHUA_SU_DUNG":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Mã OTP này đã được sử dụng hoặc không còn hiệu lực"
            )

        if now > otp_record.thoi_gian_het_han:
            otp_record.trang_thai = "HET_HAN"
            gd.trang_thai = "FAILED"
            db.commit()
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Mã OTP đã hết hạn (quá 5 phút)"
            )

        # Đánh dấu OTP đã sử dụng ngay lập tức (Chỉ được dùng 1 lần)
        otp_record.trang_thai = "DA_SU_DUNG"

        # 3. PESSIMISTIC LOCKING (SELECT ... FOR UPDATE) TRÊN NGƯỜI DÙNG & KHOẢN HỌC PHÍ
        user = (
            db.query(UserModel)
            .filter(UserModel.ma_nguoi_dung == gd.ma_nguoi_dung)
            .with_for_update()
            .first()
        )
        hp = (
            db.query(HocPhiModel)
            .filter(HocPhiModel.ma_hoc_phi == gd.ma_hoc_phi)
            .with_for_update()
            .first()
        )

        if not user or not hp:
            gd.trang_thai = "FAILED"
            db.commit()
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Không tìm thấy thông tin người dùng hoặc khoản học phí"
            )

        # --- TÌNH HUỐNG CONCURRENCY 2: Chống nhiều tài khoản thanh toán trùng 1 khoản học phí ---
        if hp.trang_thai == "DA_DONG":
            gd.trang_thai = "FAILED"
            db.commit()
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Khoản học phí này đã được thanh toán thành công bởi một giao dịch khác!"
            )

        # --- TÌNH HUỐNG CONCURRENCY 1: Chống nhiều giao dịch đồng thời làm âm số dư ---
        payment_amount = float(gd.so_tien_giao_dich)
        current_balance = float(user.so_du)
        if current_balance < payment_amount:
            gd.trang_thai = "FAILED"
            db.commit()
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Số dư khả dụng không đủ để thực hiện giao dịch!"
            )

        # 4. CẬP NHẬT DỮ LIỆU TRONG CÙNG 1 DATABASE TRANSACTION (ACID)
        new_balance = current_balance - payment_amount
        user.so_du = new_balance
        hp.trang_thai = "DA_DONG"
        gd.trang_thai = "SUCCESS"

        # Lưu thông tin để gửi email xác nhận sau khi commit (gửi về Gmail đã nhập)
        txn_id = gd.ma_giao_dich
        user_email = (
            request.email.strip()
            if request.email and request.email.strip()
            else user.email
        )
        user_full_name = user.ho_ten
        student_mssv = hp.mssv
        student_name = hp.ho_ten_sinh_vien
        semester = hp.hoc_ky

        db.commit()

        # 5. Gửi Email biên lai xác nhận giao dịch thành công qua Gmail
        confirm_email_body = (
            f"Xin chào {user_full_name},\n\n"
            f"Thông báo: Bạn đã đóng học phí THÀNH CÔNG trên hệ thống TDTU iBanking!\n"
            f"Chi tiết biên lai giao dịch:\n"
            f"- Mã giao dịch: {txn_id}\n"
            f"- Mã số sinh viên: {student_mssv}\n"
            f"- Họ và tên sinh viên: {student_name}\n"
            f"- Học kỳ: {semester}\n"
            f"- Số tiền đã thanh toán: {payment_amount:,.0f} VNĐ\n"
            f"- Số dư khả dụng còn lại: {new_balance:,.0f} VNĐ\n"
            f"- Thời gian hoàn tất: {now.strftime('%d/%m/%Y %H:%M:%S UTC')}\n"
            f"- Trạng thái học phí: ĐÃ THANH TOÁN\n\n"
            f"Cảm ơn bạn đã sử dụng dịch vụ TDTU iBanking!"
        )
        confirm_email_html = f"""
        <div style="font-family: Arial, sans-serif; max-width: 560px; margin: 0 auto; border: 1px solid #28a745; border-radius: 8px; overflow: hidden;">
            <div style="background-color: #28a745; color: white; padding: 16px 24px; font-size: 18px; font-weight: bold;">
                TDTU iBanking - Biên Lai Xác Nhận Đã Đóng Học Phí
            </div>
            <div style="padding: 20px 24px; color: #333; line-height: 1.6;">
                <p>Xin chào <strong>{user_full_name}</strong>,</p>
                <p>Hệ thống xác nhận bạn đã thanh toán học phí thành công với thông tin biên lai dưới đây:</p>
                <table style="width: 100%; border-collapse: collapse; margin: 12px 0;">
                    <tr><td style="padding: 6px 0; color: #555;">Mã giao dịch:</td><td style="padding: 6px 0; font-weight: bold;">{txn_id}</td></tr>
                    <tr><td style="padding: 6px 0; color: #555;">Mã số sinh viên:</td><td style="padding: 6px 0; font-weight: bold;">{student_mssv}</td></tr>
                    <tr><td style="padding: 6px 0; color: #555;">Họ và tên sinh viên:</td><td style="padding: 6px 0; font-weight: bold;">{student_name}</td></tr>
                    <tr><td style="padding: 6px 0; color: #555;">Học kỳ:</td><td style="padding: 6px 0; font-weight: bold;">{semester}</td></tr>
                    <tr><td style="padding: 6px 0; color: #555;">Số tiền đã đóng:</td><td style="padding: 6px 0; font-weight: bold; color: #d9534f;">{payment_amount:,.0f} VNĐ</td></tr>
                    <tr><td style="padding: 6px 0; color: #555;">Số dư khả dụng còn lại:</td><td style="padding: 6px 0; font-weight: bold; color: #28a745;">{new_balance:,.0f} VNĐ</td></tr>
                    <tr><td style="padding: 6px 0; color: #555;">Trạng thái học phí:</td><td style="padding: 6px 0; font-weight: bold; color: #28a745;">ĐÃ ĐÓNG HỌC PHÍ</td></tr>
                </table>
                <p style="font-size: 13px; color: #666;">Vui lòng lưu giữ email biên lai này để đối chiếu khi cần thiết.</p>
            </div>
        </div>
        """
        send_email_notification(
            to_email=user_email,
            subject=f"[TDTU iBanking] Biên lai xác nhận đã đóng học phí thành công - {txn_id}",
            body_text=confirm_email_body,
            html_body=confirm_email_html
        )

        confirm_payload = {
            "message": "Thanh toán học phí thành công! Email xác nhận đã được gửi.",
            "transaction_id": request.MaGiaoDich,
            "MaGiaoDich": request.MaGiaoDich,
            "status": "SUCCESS",
            "amount": payment_amount,
            "new_balance": new_balance,
            "mssv": student_mssv,
            "student_name": student_name,
            "semester": semester,
            "email_sent_to": user_email,
            "idempotency_key": idempotency_key,
            "idempotent_replay": False
        }
        if idempotency_key:
            IDEMPOTENCY_STORE[f"CONFIRM:{idempotency_key.strip()}"] = confirm_payload
        return confirm_payload

    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Lỗi hệ thống trong quá trình thanh toán: {str(e)}"
        )

@app.get("/api/v1/payments/history/{user_id}", tags=["Payment"])
@app.get("/api/v1/payment/history/{user_id}", tags=["Payment"])
def get_payment_history(user_id: int, db: Session = Depends(get_db)):
    """Lấy danh sách lịch sử giao dịch của người dùng kèm thông tin sinh viên/MSSV"""
    results = (
        db.query(GiaoDichModel, HocPhiModel)
        .outerjoin(HocPhiModel, GiaoDichModel.ma_hoc_phi == HocPhiModel.ma_hoc_phi)
        .filter(GiaoDichModel.ma_nguoi_dung == user_id)
        .order_by(GiaoDichModel.thoi_gian_tao.desc())
        .all()
    )

    return [
        {
            "MaGiaoDich": gd.ma_giao_dich,
            "MaHocPhi": gd.ma_hoc_phi,
            "MSSV": hp.mssv if hp else "N/A",
            "HoTenSinhVien": hp.ho_ten_sinh_vien if hp else "N/A",
            "HocKy": hp.hoc_ky if hp else "N/A",
            "SoTienGiaoDich": float(gd.so_tien_giao_dich),
            "NgayGiaoDich": gd.thoi_gian_tao.isoformat(),
            "TrangThai": gd.trang_thai
        }
        for gd, hp in results
    ]

@app.post("/api/v1/payments/webhook/callback", tags=["Webhook & Idempotency"])
def payment_webhook_callback(
    payload: WebhookCallbackRequest,
    idempotency_key: Optional[str] = Header(default=None, alias="Idempotency-Key"),
    db: Session = Depends(get_db)
):
    """
    Webhook Callback nhận thông báo trạng thái giao dịch (A -> B kèm Idempotency-Key).
    Đảm bảo nếu đối tác gửi lại callback nhiều lần với cùng Idempotency-Key thì hệ thống chỉ xử lý 1 lần.
    """
    ik = (idempotency_key or f"WH_{payload.MaGiaoDich}_{payload.event_type}").strip()
    cache_key = f"WEBHOOK:{ik}"
    if cache_key in IDEMPOTENCY_STORE:
        cached = dict(IDEMPOTENCY_STORE[cache_key])
        cached["idempotent_replay"] = True
        return cached

    gd = db.query(GiaoDichModel).filter(GiaoDichModel.ma_giao_dich == payload.MaGiaoDich).first()
    if not gd:
        raise HTTPException(status_code=404, detail="Không tìm thấy giao dịch cho Webhook Callback")

    resp = {
        "webhook_status": "ACKNOWLEDGED",
        "MaGiaoDich": gd.ma_giao_dich,
        "transaction_status": gd.trang_thai,
        "idempotency_key": ik,
        "idempotent_replay": False
    }
    IDEMPOTENCY_STORE[cache_key] = resp
    return resp

@app.post("/api/v1/payments/demo/reset", tags=["Demo & Testing"])
def reset_demo_data(db: Session = Depends(get_db)):
    """
    Khôi phục dữ liệu mẫu về trạng thái ban đầu để hỗ trợ chạy Concurrency Test & Demo nhiều lần trước Giảng viên.
    """
    try:
        IDEMPOTENCY_STORE.clear()
        db.query(XacThucOTPModel).delete()
        db.query(GiaoDichModel).delete()

        # Khôi phục số dư các tài khoản mẫu khớp với init.sql
        balances = {
            "khiem123": 10000000.00,
            "phuc123": 10000000.00,
            "nhi123": 10000000.00,
            "nhu123": 10000000.00,
        }
        for username, bal in balances.items():
            user = db.query(UserModel).filter(UserModel.ten_dang_nhap == username).first()
            if user:
                user.so_du = bal

        # Khôi phục trạng thái học phí khớp với init.sql
        tuition_statuses = {
            "524K0011": "CHUA_DONG",
            "523V0005": "CHUA_DONG",
            "524K0006": "DA_DONG",
            "524V0007": "CHUA_DONG",
        }
        for mssv, st in tuition_statuses.items():
            hp = db.query(HocPhiModel).filter(HocPhiModel.mssv == mssv).first()
            if hp:
                hp.trang_thai = st

        db.commit()
        return {"status": "SUCCESS", "message": "Đã khôi phục dữ liệu mẫu về trạng thái ban đầu."}
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Lỗi khi reset dữ liệu demo: {str(e)}")

