import json
import os
import uuid
import secrets
import threading
import contextvars
from contextlib import asynccontextmanager
from datetime import datetime, timedelta
from typing import List, Optional
import httpx
from fastapi import Depends, HTTPException, Header, Response, status
from pydantic import BaseModel, Field
from sqlalchemy import Column, Integer, String, Numeric, DateTime, create_engine, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, declarative_base, sessionmaker
from observability import set_request_id, tracing_headers
from security import INTERNAL_API_KEY, get_current_user_id
from service_app import create_app
from redis_cache import get_cache, set_cache, delete_cache

# 1. Cấu hình Database & Endpoint của các Service khác
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://root:rootpassword@db:5432/payment_db")
AUTH_SERVICE_URL = os.getenv("AUTH_SERVICE_URL", "http://auth-service:8001")
TUITION_SERVICE_URL = os.getenv("TUITION_SERVICE_URL", "http://tuition-service:8002")
# Gửi email (OTP, xác nhận) qua Notification Service, không gọi SMTP trực tiếp
NOTIFICATION_SERVICE_URL = os.getenv("NOTIFICATION_SERVICE_URL", "http://notification-service:8004")

OTP_TTL_MINUTES = 5
OTP_MAX_ATTEMPTS = 3

engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# 2. Database Models nội bộ của Payment Service
# (Số dư thuộc Auth Service, học phí thuộc Tuition Service -> chỉ truy cập qua REST API)
class GiaoDichModel(Base):
    __tablename__ = "GiaoDich"
    MaGiaoDich = Column(String(50), primary_key=True)
    MaNguoiDung = Column(Integer, nullable=False)
    MaHocPhi = Column(Integer, nullable=False)
    MSSV = Column(String(20), nullable=False)
    TenSinhVien = Column(String(100), nullable=False)
    SoTienGiaoDich = Column(Numeric(15, 2), nullable=False)
    NgayGiaoDich = Column(DateTime, nullable=False)
    TrangThai = Column(String(30), nullable=False)  # 'PENDING', 'PROCESSING', 'SUCCESS', 'FAILED'
    UpdatedAt = Column(DateTime, nullable=False, default=datetime.utcnow)
    IdempotencyKey = Column(String(100), nullable=True)  # duy nhất theo (MaNguoiDung, IdempotencyKey)

class XacThucOTPModel(Base):
    __tablename__ = "XacThucOTP"
    MaOTP = Column(Integer, primary_key=True, index=True)
    MaGiaoDich = Column(String(50), nullable=False)
    MaCode = Column(String(10), nullable=False)
    ThoiGianTao = Column(DateTime, nullable=False)
    ThoiGianHetHan = Column(DateTime, nullable=False)
    SoLanNhapSai = Column(Integer, nullable=False, default=0)
    TrangThai = Column(String(30), nullable=False)  # 'CHUA_SU_DUNG', 'DA_SU_DUNG'

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# 3. Khởi tạo FastAPI
_recovery_stop = threading.Event()

@asynccontextmanager
async def lifespan(app):
    # Migration cộng thêm cho DB tạo trước khi có saga recovery / Idempotency-Key
    with engine.begin() as connection:
        connection.execute(text(
            'ALTER TABLE "GiaoDich" ADD COLUMN IF NOT EXISTS "UpdatedAt" '
            'TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP'
        ))
        connection.execute(text(
            'ALTER TABLE "GiaoDich" ADD COLUMN IF NOT EXISTS "IdempotencyKey" VARCHAR(100)'
        ))
        connection.execute(text(
            'CREATE UNIQUE INDEX IF NOT EXISTS "uq_giaodich_idempotency" '
            'ON "GiaoDich" ("MaNguoiDung", "IdempotencyKey")'
        ))
    # Worker nền tự thử lại các giao dịch PROCESSING bị dở dang
    _recovery_stop.clear()
    recovery_worker = threading.Thread(
        target=_recovery_loop,
        name="payment-saga-recovery",
        daemon=True,
    )
    recovery_worker.start()
    try:
        yield
    finally:
        _recovery_stop.set()
        recovery_worker.join(timeout=10)

app, logger = create_app("Payment Service", "payment-service", docs_prefix="/api/v1/payments", lifespan=lifespan)

def internal_client() -> httpx.Client:
    """HTTP client gọi API nội bộ của Auth/Tuition/Notification Service (kèm X-Request-ID để tracing)"""
    return httpx.Client(timeout=10, headers={"X-Internal-Key": INTERNAL_API_KEY, **tracing_headers()})

# 4. Pydantic Schemas
class CreatePaymentRequest(BaseModel):
    MaHocPhi: int = Field(gt=0)

class CreatePaymentResponse(BaseModel):
    transaction_id: str
    message: str
    otp_expires_at: str

class ConfirmPaymentRequest(BaseModel):
    otp: str = Field(pattern=r"^\d{6}$")

class ConfirmPaymentResponse(BaseModel):
    message: str
    transaction_id: str
    status: str
    new_balance: float

class TransactionDetail(BaseModel):
    MaGiaoDich: str
    MaHocPhi: int
    MSSV: str
    TenSinhVien: str
    SoTienGiaoDich: float
    NgayGiaoDich: str
    TrangThai: str
    otp_expires_at: Optional[str] = None

def _iso_utc(dt: datetime) -> str:
    return dt.isoformat() + "Z"

def _error_detail(res: httpx.Response, default: str) -> str:
    try:
        return res.json().get("detail", default)
    except ValueError:
        return default

def _fail_transaction(db: Session, gd: GiaoDichModel, status_code: int, detail: str):
    gd.TrangThai = "FAILED"
    gd.UpdatedAt = datetime.utcnow()
    db.commit()
    logger.warning("Giao dịch %s -> FAILED: %s", gd.MaGiaoDich, detail)
    raise HTTPException(status_code=status_code, detail=detail)

def _retry_transaction(db: Session, gd: GiaoDichModel, detail: str, cause: Optional[Exception] = None):
    """Keep transient failures retryable without polling the same row every loop."""
    gd.UpdatedAt = datetime.utcnow()
    db.commit()
    logger.warning("Giao dịch %s vẫn PROCESSING, sẽ thử lại: %s", gd.MaGiaoDich, detail)
    error = HTTPException(status_code=503, detail=detail)
    if cause:
        raise error from cause
    raise error

def _expire_stale_transactions(db: Session, user_id: int):
    """Giao dịch PENDING có OTP đã hết hạn mà chưa xác nhận -> FAILED"""
    expired_txn_ids = select(XacThucOTPModel.MaGiaoDich).where(
        XacThucOTPModel.TrangThai == "CHUA_SU_DUNG",
        XacThucOTPModel.ThoiGianHetHan < datetime.utcnow()
    )
    db.query(GiaoDichModel).filter(
        GiaoDichModel.MaNguoiDung == user_id,
        GiaoDichModel.TrangThai == "PENDING",
        GiaoDichModel.MaGiaoDich.in_(expired_txn_ids)
    ).update({GiaoDichModel.TrangThai: "FAILED"}, synchronize_session=False)
    db.commit()

def _get_own_transaction(db: Session, transaction_id: str, user_id: int, lock: bool = False) -> GiaoDichModel:
    query = db.query(GiaoDichModel).filter(GiaoDichModel.MaGiaoDich == transaction_id)
    if lock:
        query = query.with_for_update()
    gd = query.first()
    if not gd:
        db.rollback()
        raise HTTPException(status_code=404, detail="Không tìm thấy giao dịch")
    if gd.MaNguoiDung != user_id:
        db.rollback()
        raise HTTPException(status_code=403, detail="Bạn không có quyền truy cập giao dịch này")
    return gd

def _to_detail(gd: GiaoDichModel, otp: Optional[XacThucOTPModel] = None) -> dict:
    return {
        "MaGiaoDich": gd.MaGiaoDich,
        "MaHocPhi": gd.MaHocPhi,
        "MSSV": gd.MSSV,
        "TenSinhVien": gd.TenSinhVien,
        "SoTienGiaoDich": float(gd.SoTienGiaoDich),
        "NgayGiaoDich": _iso_utc(gd.NgayGiaoDich),
        "TrangThai": gd.TrangThai,
        "otp_expires_at": _iso_utc(otp.ThoiGianHetHan) if otp else None
    }

# 5. Gửi thông báo qua Notification Service
def _notify(to: str, template: str, data: dict):
    """Gọi Notification Service gửi email theo mẫu, ném exception nếu gửi thất bại"""
    with internal_client() as client:
        res = client.post(f"{NOTIFICATION_SERVICE_URL}/api/v1/notifications", json={
            "channel": "email", "to": to, "template": template, "data": data
        })
    if not res.is_success:
        raise RuntimeError(f"Notification Service trả {res.status_code}: {_error_detail(res, res.text)}")

def _replay_idempotent_request(db: Session, gd: GiaoDichModel, request: CreatePaymentRequest, response: Response) -> dict:
    """Request lặp lại cùng Idempotency-Key: trả lại giao dịch đã tạo, không tạo mới và không gửi OTP lần hai"""
    if gd.MaHocPhi != request.MaHocPhi:
        raise HTTPException(status_code=409, detail="Idempotency-Key đã được dùng cho một yêu cầu khác")
    otp = db.query(XacThucOTPModel).filter(
        XacThucOTPModel.MaGiaoDich == gd.MaGiaoDich
    ).order_by(XacThucOTPModel.MaOTP.desc()).first()
    response.headers["Idempotent-Replayed"] = "true"
    return {
        "transaction_id": gd.MaGiaoDich,
        "message": "Giao dịch đã được tạo trước đó, mã OTP đã được gửi đến email của bạn.",
        "otp_expires_at": _iso_utc(otp.ThoiGianHetHan)
    }

def _find_by_idempotency_key(db: Session, user_id: int, key: str) -> Optional[GiaoDichModel]:
    return db.query(GiaoDichModel).filter(
        GiaoDichModel.MaNguoiDung == user_id,
        GiaoDichModel.IdempotencyKey == key
    ).first()

def _generate_unique_otp(db: Session) -> str:
    """Sinh OTP 6 số ngẫu nhiên, không trùng với OTP đang còn hiệu lực của giao dịch khác"""
    while True:
        code = f"{secrets.randbelow(1_000_000):06d}"
        in_use = db.query(XacThucOTPModel).filter(
            XacThucOTPModel.MaCode == code,
            XacThucOTPModel.TrangThai == "CHUA_SU_DUNG",
            XacThucOTPModel.ThoiGianHetHan > datetime.utcnow()
        ).first()
        if not in_use:
            return code

def _send_success_email(ma_giao_dich: str, ma_nguoi_dung: int, mssv: str, ten_sv: str, amount: str, new_balance: float):
    """Chạy nền sau khi giao dịch thành công: gửi email xác nhận cho người nộp tiền"""
    try:
        with internal_client() as client:
            user = client.get(f"{AUTH_SERVICE_URL}/api/v1/users/{ma_nguoi_dung}").json()

        _notify(user["email"], "PAYMENT_SUCCESS", {
            "full_name": user["full_name"],
            "transaction_id": ma_giao_dich,
            "mssv": mssv,
            "student_name": ten_sv,
            "amount": amount,
            "new_balance": new_balance
        })
    except Exception as e:
        logger.error("Không gửi được email xác nhận cho giao dịch %s: %s", ma_giao_dich, e)

def _continue_payment(transaction_id: str):
    """Resume a PROCESSING saga safely; downstream operations are keyed by transaction_id."""
    db = SessionLocal()
    try:
        gd = db.query(GiaoDichModel).filter(
            GiaoDichModel.MaGiaoDich == transaction_id
        ).with_for_update().first()
        if not gd or gd.TrangThai != "PROCESSING":
            db.rollback()
            return None

        amount_payload = {
            "amount": str(gd.SoTienGiaoDich),
            "transaction_id": gd.MaGiaoDich
        }
        with internal_client() as client:
            try:
                deduct_res = client.post(
                    f"{AUTH_SERVICE_URL}/api/v1/users/{gd.MaNguoiDung}/deduct-balance",
                    json=amount_payload
                )
            except httpx.HTTPError as exc:
                _retry_transaction(db, gd, "Auth Service chưa phản hồi; giao dịch sẽ được thử lại", exc)

            if deduct_res.status_code != 200:
                detail = _error_detail(deduct_res, "Không thể trừ số dư tài khoản")
                if deduct_res.status_code in (400, 404, 409):
                    _fail_transaction(db, gd, deduct_res.status_code, detail)
                _retry_transaction(db, gd, "Auth Service lỗi tạm thời; giao dịch sẽ được thử lại")

            try:
                tuition_res = client.post(
                    f"{TUITION_SERVICE_URL}/api/v1/tuitions/{gd.MaHocPhi}/pay",
                    json={"transaction_id": gd.MaGiaoDich}
                )
            except httpx.HTTPError as exc:
                _retry_transaction(db, gd, "Tuition Service chưa phản hồi; giao dịch sẽ được thử lại", exc)

            if tuition_res.status_code != 200:
                detail = _error_detail(tuition_res, "Không thể gạch nợ học phí")
                if tuition_res.status_code not in (400, 404, 409):
                    _retry_transaction(db, gd, "Tuition Service lỗi tạm thời; giao dịch sẽ được thử lại")

                # A definitive tuition rejection requires an idempotent compensation.
                try:
                    refund_res = client.post(
                        f"{AUTH_SERVICE_URL}/api/v1/users/{gd.MaNguoiDung}/refund",
                        json=amount_payload
                    )
                except httpx.HTTPError as exc:
                    _retry_transaction(db, gd, "Hoàn tiền chưa xác nhận được; giao dịch sẽ được thử lại", exc)
                if refund_res.status_code != 200:
                    _retry_transaction(db, gd, "Hoàn tiền chưa hoàn tất; giao dịch sẽ được thử lại")
                _fail_transaction(db, gd, tuition_res.status_code, detail)

        gd.TrangThai = "SUCCESS"
        gd.UpdatedAt = datetime.utcnow()
        db.commit()
        new_balance = deduct_res.json()["new_balance"]
        logger.info("Giao dịch %s -> SUCCESS (MSSV %s, %s)", gd.MaGiaoDich, gd.MSSV, gd.SoTienGiaoDich)
        # copy_context: thread gửi mail giữ nguyên request ID của request hiện tại
        threading.Thread(
            target=contextvars.copy_context().run,
            args=(_send_success_email, gd.MaGiaoDich, gd.MaNguoiDung, gd.MSSV, gd.TenSinhVien,
                  str(gd.SoTienGiaoDich), new_balance),
            daemon=True
        ).start()
        return {
            "message": "Thanh toán học phí thành công",
            "transaction_id": transaction_id,
            "status": "SUCCESS",
            "new_balance": new_balance
        }
    finally:
        db.close()

def _recovery_loop():
    """Retry old PROCESSING transactions after service restart or transient failures."""
    while not _recovery_stop.wait(5):
        db = SessionLocal()
        try:
            cutoff = datetime.utcnow() - timedelta(seconds=15)
            transaction_ids = [row[0] for row in db.query(GiaoDichModel.MaGiaoDich).filter(
                GiaoDichModel.TrangThai == "PROCESSING",
                GiaoDichModel.UpdatedAt < cutoff
            ).order_by(GiaoDichModel.UpdatedAt.asc()).limit(20).all()]
        except Exception as exc:
            logger.error("Không đọc được giao dịch cần phục hồi: %s", exc)
            transaction_ids = []
        finally:
            db.close()
        for transaction_id in transaction_ids:
            # Mỗi lần phục hồi có request ID riêng để lần theo qua Auth/Tuition/Notification
            set_request_id(f"recovery-{uuid.uuid4().hex[:12]}")
            logger.info("Phục hồi giao dịch %s", transaction_id)
            try:
                _continue_payment(transaction_id)
            except HTTPException as exc:
                logger.info("Phục hồi giao dịch %s chưa xong: %s", transaction_id, exc.detail)
            except Exception as exc:
                logger.error("Không phục hồi được giao dịch %s: %s", transaction_id, exc)

# 6. API Endpoints
# Lưu ý: dùng `def` (không phải `async def`) để FastAPI chạy trong threadpool,
# tránh việc truy vấn DB có khoá dòng chặn event loop khi nhiều request đồng thời.

@app.post("/api/v1/payments", response_model=CreatePaymentResponse, status_code=status.HTTP_201_CREATED, tags=["Payment"])
def create_payment(
    request: CreatePaymentRequest,
    response: Response,
    user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db),
    idempotency_key: Optional[str] = Header(None, min_length=1, max_length=100)
):
    """
    Khởi tạo giao dịch: kiểm tra số dư (Auth Service) và khoản học phí (Tuition Service),
    tạo giao dịch PENDING và gửi OTP qua email người nộp tiền.

    Header `Idempotency-Key` (tuỳ chọn): gửi lại cùng khoá (bấm nút 2 lần, mạng chập chờn
    tự gửi lại) sẽ nhận về giao dịch đã tạo thay vì tạo giao dịch và OTP mới.
    """
    try:
        with internal_client() as client:
            # Gọi Auth Service lấy thông tin người dùng & số dư
            user_res = client.get(f"{AUTH_SERVICE_URL}/api/v1/users/{user_id}")
            # Gọi Tuition Service lấy thông tin khoản học phí
            tuition_res = client.get(f"{TUITION_SERVICE_URL}/api/v1/tuitions/detail/{request.MaHocPhi}")
    except httpx.HTTPError:
        raise HTTPException(status_code=503, detail="Không kết nối được tới Auth/Tuition Service")

    if user_res.status_code != 200:
        raise HTTPException(status_code=404, detail="Không tìm thấy người dùng")
    if tuition_res.status_code == 404:
        raise HTTPException(status_code=404, detail="Không tìm thấy khoản học phí")
    if tuition_res.status_code != 200:
        raise HTTPException(status_code=502, detail="Tuition Service phản hồi lỗi")
    user_data = user_res.json()
    tuition_data = tuition_res.json()

    if idempotency_key:
        existing = _find_by_idempotency_key(db, user_id, idempotency_key)
        if existing:
            return _replay_idempotent_request(db, existing, request, response)
    delete_cache(f"payment_history:{user_id}")
    if tuition_data["TrangThai"] != "CHUA_DONG":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Khoản học phí này đã được thanh toán"
        )

    # Kiểm tra số dư khả dụng
    if float(user_data["available_balance"]) < float(tuition_data["SoTienPhaiNop"]):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Số dư khả dụng không đủ để thực hiện giao dịch"
        )

    # Tạo giao dịch PENDING (uuid để không trùng mã khi nhiều giao dịch tạo cùng lúc)
    ma_giao_dich = f"TXN_{uuid.uuid4().hex}"
    now = datetime.utcnow()
    gd = GiaoDichModel(
        MaGiaoDich=ma_giao_dich,
        MaNguoiDung=user_id,
        MaHocPhi=request.MaHocPhi,
        MSSV=tuition_data["MSSV"],
        TenSinhVien=tuition_data["HoTen"],
        SoTienGiaoDich=tuition_data["SoTienPhaiNop"],
        NgayGiaoDich=now,
        TrangThai="PENDING",
        IdempotencyKey=idempotency_key
    )
    db.add(gd)

    # Sinh OTP 6 số ngẫu nhiên gắn với giao dịch, hết hạn sau 5 phút
    ma_code = _generate_unique_otp(db)
    otp = XacThucOTPModel(
        MaGiaoDich=ma_giao_dich,
        MaCode=ma_code,
        ThoiGianTao=now,
        ThoiGianHetHan=now + timedelta(minutes=OTP_TTL_MINUTES),
        SoLanNhapSai=0,
        TrangThai="CHUA_SU_DUNG"
    )
    db.add(otp)
    try:
        db.commit()
    except IntegrityError:
        # 2 request cùng Idempotency-Key tới đồng thời: request sau vướng ràng buộc UNIQUE
        # (MaNguoiDung, IdempotencyKey) -> trả lại giao dịch mà request trước đã tạo
        db.rollback()
        existing = _find_by_idempotency_key(db, user_id, idempotency_key) if idempotency_key else None
        if not existing:
            raise
        return _replay_idempotent_request(db, existing, request, response)

    # Gửi OTP qua email của người nộp tiền (qua Notification Service)
    try:
        _notify(user_data["email"], "OTP", {
            "full_name": user_data["full_name"],
            "mssv": tuition_data["MSSV"],
            "student_name": tuition_data["HoTen"],
            "amount": tuition_data["SoTienPhaiNop"],
            "otp": ma_code,
            "ttl_minutes": OTP_TTL_MINUTES,
            "transaction_id": ma_giao_dich
        })
    except Exception as e:
        logger.error("Không gửi được email OTP cho giao dịch %s: %s", ma_giao_dich, e)
        _fail_transaction(db, gd, status.HTTP_502_BAD_GATEWAY, "Không gửi được email OTP, vui lòng thử lại sau")

    logger.info("Tạo giao dịch %s: MaNguoiDung=%s trả MSSV %s (%s), đã gửi OTP",
                ma_giao_dich, user_id, tuition_data["MSSV"], tuition_data["SoTienPhaiNop"])

    return {
        "transaction_id": ma_giao_dich,
        "message": "OTP đã được gửi đến email của bạn.",
        "otp_expires_at": _iso_utc(otp.ThoiGianHetHan)
    }

@app.post("/api/v1/payments/{transaction_id}/confirm", response_model=ConfirmPaymentResponse, tags=["Payment"])
def confirm_payment(
    transaction_id: str,
    request: ConfirmPaymentRequest,
    user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db)
):
    """
    Xác nhận OTP, trừ tiền tài khoản, gạch nợ học phí và lưu lịch sử
    """
    # --- BƯỚC 1: Khoá giao dịch để 2 request confirm cùng lúc không xử lý trùng ---
    gd = _get_own_transaction(db, transaction_id, user_id, lock=True)

    if gd.TrangThai != "PENDING":
        db.rollback()
        raise HTTPException(status_code=409, detail="Giao dịch này đã được xử lý trước đó")

    otp = db.query(XacThucOTPModel).filter(
        XacThucOTPModel.MaGiaoDich == transaction_id,
        XacThucOTPModel.TrangThai == "CHUA_SU_DUNG"
    ).first()

    if not otp or datetime.utcnow() > otp.ThoiGianHetHan:
        _fail_transaction(db, gd, status.HTTP_400_BAD_REQUEST,
                          "Mã OTP đã hết hạn, vui lòng tạo giao dịch mới")

    if otp.MaCode != request.otp:
        otp.SoLanNhapSai += 1
        if otp.SoLanNhapSai >= OTP_MAX_ATTEMPTS:
            otp.TrangThai = "DA_SU_DUNG"
            _fail_transaction(db, gd, status.HTTP_400_BAD_REQUEST,
                              f"Bạn đã nhập sai OTP {OTP_MAX_ATTEMPTS} lần. Giao dịch đã bị huỷ.")
        db.commit()
        remaining = OTP_MAX_ATTEMPTS - otp.SoLanNhapSai
        raise HTTPException(status_code=400, detail=f"Mã OTP không chính xác (còn {remaining} lần thử)")

    # Vô hiệu hóa OTP ngay lập tức sau 1 lần dùng
    otp.TrangThai = "DA_SU_DUNG"
    gd.TrangThai = "PROCESSING"
    gd.UpdatedAt = datetime.utcnow()
    db.commit()
    logger.info("Giao dịch %s: OTP hợp lệ -> PROCESSING, bắt đầu trừ tiền và gạch nợ", transaction_id)
    result = _continue_payment(transaction_id)
    if result is None:
        raise HTTPException(status_code=409, detail="Giao dịch đã được xử lý")
    delete_cache(f"payment_history:{user_id}")
    return result

@app.get("/api/v1/payments", response_model=List[TransactionDetail], tags=["Payment"])
def get_payment_history(user_id: int = Depends(get_current_user_id), db: Session = Depends(get_db)):
    """Lấy lịch sử giao dịch của người dùng đang đăng nhập"""
    _expire_stale_transactions(db, user_id)
    cached_key = f"payment_history:{user_id}"
    cached_data = get_cache(cached_key)
    if cached_data:
        logger.info("Lấy lịch sử giao dịch của user %s từ Redis cache", user_id)
        return cached_data
    
    history = (
        db.query(GiaoDichModel)
        .filter(GiaoDichModel.MaNguoiDung == user_id)
        .order_by(GiaoDichModel.NgayGiaoDich.desc())
        .all()
    )
    result = [_to_detail(item) for item in history]
    set_cache(cached_key, result, 120) 
    return result

@app.get("/api/v1/payments/{transaction_id}", response_model=TransactionDetail, tags=["Payment"])
def get_payment(transaction_id: str, user_id: int = Depends(get_current_user_id), db: Session = Depends(get_db)):
    """Xem chi tiết một giao dịch (kèm thời điểm hết hạn OTP nếu đang chờ xác nhận)"""
    _expire_stale_transactions(db, user_id)
    gd = _get_own_transaction(db, transaction_id, user_id)
    otp = None
    if gd.TrangThai == "PENDING":
        otp = db.query(XacThucOTPModel).filter(
            XacThucOTPModel.MaGiaoDich == transaction_id,
            XacThucOTPModel.TrangThai == "CHUA_SU_DUNG"
        ).first()
    return _to_detail(gd, otp)
