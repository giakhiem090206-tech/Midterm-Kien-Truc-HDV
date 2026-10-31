import os
import random
from datetime import datetime, timedelta
import httpx
from fastapi import FastAPI, Depends, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sqlalchemy import Column, Integer, String, Numeric, DateTime, create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import Session, sessionmaker

# 1. Cấu hình Database & Endpoint của các Service khác
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://root:rootpassword@db:5432/ibanking")
AUTH_SERVICE_URL = os.getenv("AUTH_SERVICE_URL", "http://auth-service:8001")
TUITION_SERVICE_URL = os.getenv("TUITION_SERVICE_URL", "http://tuition-service:8002")

engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# 2. Database Models nội bộ của Payment Service
class GiaoDichModel(Base):
    __tablename__ = "GiaoDich"
    MaGiaoDich = Column(String(50), primary_key=True)
    MaNguoiDung = Column(Integer, nullable=False)
    MaHocPhi = Column(Integer, nullable=False)
    SoTienGiaoDich = Column(Numeric(15, 2), nullable=False)
    NgayGiaoDich = Column(DateTime, nullable=False)
    TrangThai = Column(String(30), nullable=False)  # 'PENDING', 'SUCCESS', 'FAILED'

class XacThucOTPModel(Base):
    __tablename__ = "XacThucOTP"
    MaOTP = Column(Integer, primary_key=True, index=True)
    MaGiaoDich = Column(String(50), nullable=False)
    MaCode = Column(String(10), nullable=False)
    ThoiGianTao = Column(DateTime, nullable=False)
    ThoiGianHetHan = Column(DateTime, nullable=False)
    TrangThai = Column(String(30), nullable=False)  # 'CHUA_SU_DUNG', 'DA_SU_DUNG'

# Khai báo bổ sung UserModel và HocPhiModel cho hàm confirm_payment dùng Pessimistic Locking
class UserModel(Base):
    __tablename__ = "NguoiDung"
    MaNguoiDung = Column(Integer, primary_key=True)
    SoDuKhaDung = Column(Numeric(15, 2), nullable=False)

class HocPhiModel(Base):
    __tablename__ = "HocPhi"
    MaHocPhi = Column(Integer, primary_key=True)
    TrangThai = Column(String(30), nullable=False)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# 3. Khởi tạo FastAPI & CORS
app = FastAPI(title="Payment Service", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 4. Pydantic Schemas
class InitiatePaymentRequest(BaseModel):
    MaNguoiDung: int
    MaHocPhi: int

class InitiatePaymentResponse(BaseModel):
    transaction_id: str
    message: str

class ConfirmPaymentRequest(BaseModel):
    MaGiaoDich: str
    otp: str

class TransactionResponse(BaseModel):
    message: str
    transaction_id: str
    status: str

# 5. API Endpoints

@app.post("/api/v1/payments/initiate", response_model=InitiatePaymentResponse, status_code=status.HTTP_201_CREATED, tags=["Payment"])
async def initiate_payment(
    request: InitiatePaymentRequest,
    db: Session = Depends(get_db)
):
    """
    1. Khởi tạo giao dịch: Gọi Auth Service kiểm tra số dư và Tuition Service kiểm tra khoản nộp
    """
    async with httpx.AsyncClient() as client:
        # Gọi Auth Service lấy thông tin người dùng & số dư
        user_res = await client.get(f"{AUTH_SERVICE_URL}/api/v1/users/{request.MaNguoiDung}")
        if user_res.status_code != 200:
            raise HTTPException(status_code=400, detail="Người dùng không hợp lệ")
        user_data = user_res.json()

        # Gọi Tuition Service lấy thông tin khoản học phí
        tuition_res = await client.get(f"{TUITION_SERVICE_URL}/api/v1/tuitions/detail/{request.MaHocPhi}")
        if tuition_res.status_code != 200:
            raise HTTPException(status_code=400, detail="Khoản học phí không hợp lệ")
        tuition_data = tuition_res.json()

    # Kiểm tra số dư khả dụng
    if float(user_data["available_balance"]) < float(tuition_data["SoTienPhaiNop"]):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Số dư khả dụng không đủ để thực hiện giao dịch"
        )

    # Tạo giao dịch PENDING
    ma_giao_dich = f"TXN_{int(datetime.utcnow().timestamp())}"

    # Chống payment trùng: nếu đã có giao dịch thành công cho cùng user + hocphi, từ chối
    existing = db.query(GiaoDichModel).filter(
        GiaoDichModel.MaNguoiDung == request.MaNguoiDung,
        GiaoDichModel.MaHocPhi == request.MaHocPhi,
        GiaoDichModel.TrangThai.in_(["PENDING", "SUCCESS"])
    ).first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Khoản học phí này đã có giao dịch đang xử lý hoặc đã hoàn tất."
        )

    gd = GiaoDichModel(
        MaGiaoDich=ma_giao_dich,
        MaNguoiDung=request.MaNguoiDung,
        MaHocPhi=request.MaHocPhi,
        SoTienGiaoDich=tuition_data["SoTienPhaiNop"],
        NgayGiaoDich=datetime.utcnow(),
        TrangThai="PENDING"
    )
    db.add(gd)

    # Sinh OTP 6 số ngẫu nhiên, hết hạn trong 5 phút
    ma_code = f"{random.randint(100000, 999999)}"
    otp = XacThucOTPModel(
        MaGiaoDich=ma_giao_dich,
        MaCode=ma_code,
        ThoiGianTao=datetime.utcnow(),
        ThoiGianHetHan=datetime.utcnow() + timedelta(minutes=5),
        TrangThai="CHUA_SU_DUNG"
    )
    db.add(otp)
    db.commit()

    print(f"[SIMULATION] Gửi OTP {ma_code} đến email: {user_data.get('email')}")

    return {
        "transaction_id": ma_giao_dich,
        "message": "OTP đã được gửi đến email của bạn."
    }

@app.get("/api/v1/payments/qr/{transaction_id}", tags=["Payment"])
def get_payment_qr(transaction_id: str, db: Session = Depends(get_db)):
    """Trả về dữ liệu QR giả lập cho thao tác quét QR của người dùng."""
    gd = db.query(GiaoDichModel).filter(GiaoDichModel.MaGiaoDich == transaction_id).first()
    if not gd:
        raise HTTPException(status_code=404, detail="Không tìm thấy giao dịch")

    qr_data = f"IBANKING|{transaction_id}|{gd.MaNguoiDung}|{float(gd.SoTienGiaoDich)}|TDTU"
    return {
        "transaction_id": transaction_id,
        "amount": float(gd.SoTienGiaoDich),
        "merchant": "TDTU iBanking",
        "qr_data": qr_data
    }

@app.post("/api/v1/payments/confirm", response_model=TransactionResponse, tags=["Payment"])
async def confirm_payment(
    request: ConfirmPaymentRequest,
    db: Session = Depends(get_db)
):
    """
    5. Xác nhận OTP, trừ tiền tài khoản, gạch nợ học phí và lưu lịch sử
    """
    otp = db.query(XacThucOTPModel).filter(
        XacThucOTPModel.MaGiaoDich == request.MaGiaoDich,
        XacThucOTPModel.MaCode == request.otp,
        XacThucOTPModel.TrangThai == "CHUA_SU_DUNG"
    ).first()

    if not otp or datetime.utcnow() > otp.ThoiGianHetHan:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Mã OTP không hợp lệ hoặc đã hết hạn"
        )

    # Vô hiệu hóa OTP ngay lập tức sau 1 lần dùng
    otp.TrangThai = "DA_SU_DUNG"

    gd = db.query(GiaoDichModel).filter(GiaoDichModel.MaGiaoDich == request.MaGiaoDich).first()
    if not gd:
        raise HTTPException(status_code=404, detail="Không tìm thấy giao dịch")

    if gd.TrangThai == "SUCCESS":
        raise HTTPException(status_code=400, detail="Giao dịch này đã được xác nhận trước đó")

    gd.TrangThai = "SUCCESS"

    # Trừ tiền người dùng và gạch nợ học phí
    try:
        # 6: ÁP DỤNG KHOÁ DÒNG (PESSIMISTIC LOCKING) VỚI .with_for_update() ---
        user = db.query(UserModel).filter(UserModel.MaNguoiDung == gd.MaNguoiDung).with_for_update().first()
        hp = db.query(HocPhiModel).filter(HocPhiModel.MaHocPhi == gd.MaHocPhi).with_for_update().first()

        if not user or not hp:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Không tìm thấy thông tin người dùng hoặc khoản học phí"
            )

        # --- CHỐNG ÂM SỐ DƯ (Kiểm tra lại sau khi lấy lock) ---
        if float(user.SoDuKhaDung) < float(gd.SoTienGiaoDich):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Số dư tài khoản không đủ để thực hiện giao dịch!"
            )
            
        # --- CHỐNG THANH TOÁN TRÙNG (Kiểm tra trạng thái học phí) ---
        if hp.TrangThai == "DA_DONG":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Khoản học phí này đã được thanh toán thành công trước đó!"
            )

        # --- CẬP NHẬT DỮ LIỆU ---
        user.SoDuKhaDung = float(user.SoDuKhaDung) - float(gd.SoTienGiaoDich)
        hp.TrangThai = "DA_DONG"

        db.commit()

        return {
            "message": "Thanh toán học phí thành công",
            "transaction_id": request.MaGiaoDich,
            "status": "SUCCESS"
        }

    except HTTPException as he:
        db.rollback()
        raise he
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Lỗi hệ thống trong quá trình thanh toán: {str(e)}"
        )

@app.get("/api/v1/payments/history/{user_id}", tags=["Payment"])
@app.get("/api/v1/payment/history/{user_id}", tags=["Payment"])
def get_payment_history(user_id: int, db: Session = Depends(get_db)):
    """Lấy danh sách lịch sử giao dịch của người dùng"""
    history = (
        db.query(GiaoDichModel)
        .filter(GiaoDichModel.MaNguoiDung == user_id)
        .order_by(GiaoDichModel.NgayGiaoDich.desc())
        .all()
    )

    return [
        {
            "MaGiaoDich": item.MaGiaoDich,
            "SoTienGiaoDich": float(item.SoTienGiaoDich),
            "NgayGiaoDich": item.NgayGiaoDich.isoformat(),
            "TrangThai": item.TrangThai
        }
        for item in history
    ]