import os
import re
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from decimal import Decimal
import jwt
from fastapi import Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import Column, Integer, String, Numeric, DateTime, UniqueConstraint, create_engine
from sqlalchemy.orm import Session, declarative_base, sessionmaker
from security import JWT_SECRET, get_current_user_id, verify_internal_key
from service_app import create_app
from redis_cache import get_cache, set_cache, delete_cache

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://root:rootpassword@db:5432/auth_db")
JWT_EXPIRE_MINUTES = int(os.getenv("JWT_EXPIRE_MINUTES", "60"))

engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

class UserModel(Base):
    __tablename__ = "NguoiDung"
    MaNguoiDung = Column(Integer, primary_key=True, index=True)
    TenDangNhap = Column(String(50), unique=True, nullable=False)
    MatKhau = Column(String(255), nullable=False)
    HoTen = Column(String(100), nullable=False)
    SoDienThoai = Column(String(20), nullable=False)
    Email = Column(String(100), nullable=False)
    SoDuKhaDung = Column(Numeric(15, 2), nullable=False)

class BalanceOperationModel(Base):
    __tablename__ = "BalanceOperation"
    __table_args__ = (UniqueConstraint("MaGiaoDich", "Loai", name="uq_balance_operation_txn_type"),)
    MaOperation = Column(Integer, primary_key=True)
    MaGiaoDich = Column(String(50), nullable=False)
    Loai = Column(String(10), nullable=False)
    SoTien = Column(Numeric(15, 2), nullable=False)
    SoDuSau = Column(Numeric(15, 2), nullable=False)
    NgayTao = Column(DateTime, nullable=False)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

@asynccontextmanager
async def lifespan(app):
    BalanceOperationModel.__table__.create(bind=engine, checkfirst=True)
    yield

app, logger = create_app("Auth Service", "auth-service", docs_prefix="/api/v1/auth", lifespan=lifespan)

class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=50)
    password: str = Field(min_length=1, max_length=255)

class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    MaNguoiDung: int
    HoTen: str

class UserProfileResponse(BaseModel):
    MaNguoiDung: int
    full_name: str
    phone: str
    email: str
    student_id: str
    available_balance: float

class BalanceChangeRequest(BaseModel):
    amount: Decimal = Field(gt=0)
    transaction_id: str = Field(min_length=1, max_length=50)

class BalanceChangeResponse(BaseModel):
    status: str
    MaNguoiDung: int
    new_balance: float

def _to_profile(user: UserModel) -> dict:
    email = user.Email.strip()
    email_match = re.fullmatch(r"([A-Za-z0-9]{6,20})@student\.tdtu\.edu\.vn", email, re.IGNORECASE)
    return {
        "MaNguoiDung": user.MaNguoiDung,
        "full_name": user.HoTen,
        "phone": user.SoDienThoai,
        "email": email,
        "student_id": email_match.group(1).upper() if email_match else "",
        "available_balance": float(user.SoDuKhaDung)
    }


@app.post("/api/v1/auth/login", response_model=LoginResponse, tags=["Auth"])
def login(request: LoginRequest, db: Session = Depends(get_db)):
    """Login --> Return JWT token in sessionStorage"""
    user = db.query(UserModel).filter(
        UserModel.TenDangNhap == request.username,
        UserModel.MatKhau == request.password
    ).first()

    if not user:
        logger.warning("Đăng nhập thất bại: %s", request.username)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Sai tên đăng nhập hoặc mật khẩu"
        )

    logger.info("Đăng nhập thành công: %s (MaNguoiDung=%s)", request.username, user.MaNguoiDung)
    expires_at = datetime.now(timezone.utc) + timedelta(minutes=JWT_EXPIRE_MINUTES)
    token = jwt.encode({"sub": str(user.MaNguoiDung), "exp": expires_at}, JWT_SECRET, algorithm="HS256")

    return {
        "access_token": token,
        "token_type": "bearer",
        "expires_in": JWT_EXPIRE_MINUTES * 60,
        "MaNguoiDung": user.MaNguoiDung,
        "HoTen": user.HoTen
    }

@app.get("/api/v1/users/me", response_model=UserProfileResponse, tags=["User"])
def get_my_profile(user_id: int = Depends(get_current_user_id), db: Session = Depends(get_db)):
    """Get data of current user (from JWT token)"""
    cached_key = f"user_profile:{user_id}"
    cached_data = get_cache(cached_key)
    if cached_data:
        logger.info("Lấy thông tin user %s từ Redis cache", user_id)
        return cached_data
    
    user = db.query(UserModel).filter(UserModel.MaNguoiDung == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Không tìm thấy người dùng")
    
    profile = _to_profile(user)
    set_cache(cached_key, profile, 300) 
    return profile

@app.get("/api/v1/users/{user_id}", response_model=UserProfileResponse, tags=["User Internal"],
         dependencies=[Depends(verify_internal_key)])
def get_user_by_id(user_id: int, db: Session = Depends(get_db)):
    """API: Get information of a user by ID for other services to call"""
    cached_key = f"user_profile:{user_id}"
    cached_data = get_cache(cached_key)
    if cached_data:
        logger.info("Lấy thông tin user %s từ Redis cache", user_id)
        return cached_data
    
    user = db.query(UserModel).filter(UserModel.MaNguoiDung == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Không tìm thấy người dùng")
    profile = _to_profile(user)
    set_cache(cached_key, profile, 300)
    return profile

@app.post("/api/v1/users/{user_id}/deduct-balance", response_model=BalanceChangeResponse, tags=["User Internal"],
          dependencies=[Depends(verify_internal_key)])
def deduct_balance(user_id: int, request: BalanceChangeRequest, db: Session = Depends(get_db)):
    user = db.query(UserModel).filter(UserModel.MaNguoiDung == user_id).with_for_update().first()
    if not user:
        db.rollback()
        raise HTTPException(status_code=404, detail="Người dùng không tồn tại")

    previous = db.query(BalanceOperationModel).filter(
        BalanceOperationModel.MaGiaoDich == request.transaction_id,
        BalanceOperationModel.Loai == "DEBIT"
    ).first()
    if previous:
        if previous.SoTien != request.amount:
            db.rollback()
            raise HTTPException(status_code=409, detail="Mã giao dịch đã được dùng với số tiền khác")
        db.rollback()
        logger.info("Giao dịch %s đã trừ tiền trước đó, trả lại kết quả cũ (idempotent)", request.transaction_id)
        return {"status": "SUCCESS", "MaNguoiDung": user_id, "new_balance": float(user.SoDuKhaDung)}

    if user.SoDuKhaDung < request.amount:
        db.rollback()
        logger.warning("Giao dịch %s: số dư %s không đủ để trừ %s", request.transaction_id, user.SoDuKhaDung, request.amount)
        raise HTTPException(status_code=400, detail="Số dư khả dụng không đủ")

    user.SoDuKhaDung = user.SoDuKhaDung - request.amount
    db.add(BalanceOperationModel(
        MaGiaoDich=request.transaction_id, Loai="DEBIT", SoTien=request.amount,
        SoDuSau=user.SoDuKhaDung, NgayTao=datetime.now(timezone.utc).replace(tzinfo=None)
    ))
    db.commit()
    logger.info("Giao dịch %s: trừ %s của MaNguoiDung=%s, số dư còn %s",
                request.transaction_id, request.amount, user_id, user.SoDuKhaDung)
    delete_cache(f"user_profile:{user_id}") 
    return {
        "status": "SUCCESS",
        "MaNguoiDung": user_id,
        "new_balance": float(user.SoDuKhaDung)
    }

@app.post("/api/v1/users/{user_id}/refund", response_model=BalanceChangeResponse, tags=["User Internal"],
          dependencies=[Depends(verify_internal_key)])
def refund_balance(user_id: int, request: BalanceChangeRequest, db: Session = Depends(get_db)):
    """API: Payment Service refund money to user after a failed transaction"""
    debit = db.query(BalanceOperationModel).filter(
        BalanceOperationModel.MaGiaoDich == request.transaction_id,
        BalanceOperationModel.Loai == "DEBIT"
    ).first()
    if not debit or debit.SoTien != request.amount:
        raise HTTPException(status_code=409, detail="Không tìm thấy giao dịch trừ tiền tương ứng để hoàn")

    user = db.query(UserModel).filter(UserModel.MaNguoiDung == user_id).with_for_update().first()
    if not user:
        db.rollback()
        raise HTTPException(status_code=404, detail="Người dùng không tồn tại")

    previous = db.query(BalanceOperationModel).filter(
        BalanceOperationModel.MaGiaoDich == request.transaction_id,
        BalanceOperationModel.Loai == "REFUND"
    ).first()
    if previous:
        if previous.SoTien != request.amount:
            db.rollback()
            raise HTTPException(status_code=409, detail="Mã giao dịch đã được hoàn với số tiền khác")
        db.rollback()
        return {"status": "SUCCESS", "MaNguoiDung": user_id, "new_balance": float(user.SoDuKhaDung)}

    user.SoDuKhaDung = user.SoDuKhaDung + request.amount
    db.add(BalanceOperationModel(
        MaGiaoDich=request.transaction_id, Loai="REFUND", SoTien=request.amount,
        SoDuSau=user.SoDuKhaDung, NgayTao=datetime.now(timezone.utc).replace(tzinfo=None)
    ))
    db.commit()
    logger.info("Giao dịch %s: hoàn %s cho MaNguoiDung=%s, số dư còn %s",
                request.transaction_id, request.amount, user_id, user.SoDuKhaDung)
    delete_cache(f"user_profile:{user_id}")
    return {
        "status": "SUCCESS",
        "MaNguoiDung": user_id,
        "new_balance": float(user.SoDuKhaDung)
    }
