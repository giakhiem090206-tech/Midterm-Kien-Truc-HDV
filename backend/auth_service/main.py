import os
from typing import Optional
from fastapi import FastAPI, Depends, HTTPException, status, Header
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sqlalchemy import Column, Integer, String, Numeric, create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import Session, sessionmaker

# 1. Cấu hình Database
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://root:rootpassword@db:5432/ibanking")
engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# 2. Model "NguoiDung"
class UserModel(Base):
    __tablename__ = "NguoiDung"
    MaNguoiDung = Column(Integer, primary_key=True, index=True)
    TenDangNhap = Column(String(50), unique=True, nullable=False)
    MatKhau = Column(String(255), nullable=False)
    HoTen = Column(String(100), nullable=False)
    Email = Column(String(100), nullable=False)
    SoDuKhaDung = Column(Numeric(15, 2), nullable=False)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# 3. FastAPI Initialization & CORS
app = FastAPI(title="Auth Service", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 4. Pydantic Schemas
class LoginRequest(BaseModel):
    username: str
    password: str

class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    MaNguoiDung: int
    HoTen: str

class UserProfileResponse(BaseModel):
    MaNguoiDung: int
    full_name: str
    email: str
    available_balance: float

class ValidateTokenResponse(BaseModel):
    valid: bool
    user_id: Optional[int] = None
    full_name: Optional[str] = None

class DeductBalanceRequest(BaseModel):
    amount: float

# 5. API Endpoints

@app.post("/api/v1/auth/login", response_model=LoginResponse, tags=["Auth"])
def login(request: LoginRequest, db: Session = Depends(get_db)):
    """Đăng nhập tài khoản hệ thống"""
    user = db.query(UserModel).filter(
        UserModel.TenDangNhap == request.username,
        UserModel.MatKhau == request.password
    ).first()

    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Sai tên đăng nhập hoặc mật khẩu"
        )

    token = f"mock_jwt_token_{user.MaNguoiDung}_{user.TenDangNhap}"
    return {
        "access_token": token,
        "token_type": "bearer",
        "MaNguoiDung": user.MaNguoiDung,
        "HoTen": user.HoTen
    }

@app.get("/api/v1/auth/validate", response_model=ValidateTokenResponse, tags=["Auth"])
def validate_token(authorization: Optional[str] = Header(default=None, alias="Authorization"), db: Session = Depends(get_db)):
    """Xác thực giả lập JWT để frontend có thể kiểm tra trạng thái login."""
    if not authorization or not authorization.startswith("Bearer "):
        return {"valid": False}

    token = authorization.replace("Bearer ", "", 1)
    if not token or "mock_jwt_token_" not in token:
        return {"valid": False}

    user_id = token.split("mock_jwt_token_")[-1].split("_")[0]
    try:
        user = db.query(UserModel).filter(UserModel.MaNguoiDung == int(user_id)).first()
    except ValueError:
        return {"valid": False}

    if not user:
        return {"valid": False}

    return {
        "valid": True,
        "user_id": user.MaNguoiDung,
        "full_name": user.HoTen
    }

@app.get("/api/v1/users/me", response_model=UserProfileResponse, tags=["User"])
def get_my_profile(db: Session = Depends(get_db)):
    """Lấy thông tin tài khoản người dùng mặc định (phuc123)"""
    user = db.query(UserModel).filter(UserModel.TenDangNhap == "phuc123").first()
    if not user:
        raise HTTPException(status_code=404, detail="Không tìm thấy người dùng")
    
    return {
        "MaNguoiDung": user.MaNguoiDung,
        "full_name": user.HoTen,
        "email": user.Email,
        "available_balance": float(user.SoDuKhaDung)
    }

@app.get("/api/v1/users/{user_id}", response_model=UserProfileResponse, tags=["User Internal"])
def get_user_by_id(user_id: int, db: Session = Depends(get_db)):
    """API nội bộ: Lấy thông tin người dùng theo ID cho các Service khác gọi"""
    user = db.query(UserModel).filter(UserModel.MaNguoiDung == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Không tìm thấy người dùng")
    
    return {
        "MaNguoiDung": user.MaNguoiDung,
        "full_name": user.HoTen,
        "email": user.Email,
        "available_balance": float(user.SoDuKhaDung)
    }

@app.post("/api/v1/users/{user_id}/deduct-balance", tags=["User Internal"])
def deduct_balance(user_id: int, request: DeductBalanceRequest, db: Session = Depends(get_db)):
    """API nội bộ: Được gọi bởi Payment Service để trừ số dư tài khoản"""
    user = db.query(UserModel).filter(UserModel.MaNguoiDung == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Người dùng không tồn tại")
    
    current_balance = float(user.SoDuKhaDung)
    if current_balance < request.amount:
        raise HTTPException(status_code=400, detail="Số dư khả dụng không đủ")
    
    user.SoDuKhaDung = current_balance - request.amount
    db.commit()
    
    return {
        "status": "SUCCESS",
        "MaNguoiDung": user_id,
        "new_balance": float(user.SoDuKhaDung)
    }