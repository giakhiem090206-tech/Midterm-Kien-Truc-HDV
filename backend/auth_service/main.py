import os
from typing import Optional
from fastapi import FastAPI, Depends, HTTPException, status, Header
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from sqlalchemy import Column, Integer, String, Numeric, create_engine, or_, func
from sqlalchemy.orm import declarative_base, Session, sessionmaker

# 1. Cấu hình Database
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://root:rootpassword@db:5432/ibanking")
engine = create_engine(DATABASE_URL, pool_pre_ping=True)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# 2. Model "nguoi_dung" (đồng bộ 100% với init.sql)
class UserModel(Base):
    __tablename__ = "nguoi_dung"
    ma_nguoi_dung = Column(Integer, primary_key=True, index=True)
    mssv = Column(String(20), unique=True, nullable=False, index=True)
    ten_dang_nhap = Column(String(50), unique=True, nullable=False)
    mat_khau = Column(String(255), nullable=False)
    ho_ten = Column(String(100), nullable=False)
    so_dien_thoai = Column(String(20), nullable=False)
    email = Column(String(100), unique=True, nullable=False)
    so_du = Column(Numeric(15, 2), nullable=False)

Base.metadata.create_all(bind=engine)

def ensure_seed_users():
    db = SessionLocal()
    try:
        if db.query(UserModel).count() == 0:
            db.add_all([
                UserModel(
                    mssv="524K0006",
                    ten_dang_nhap="khiem123",
                    mat_khau="123456",
                    ho_ten="Thân Vũ Gia Khiêm",
                    so_dien_thoai="0901111111",
                    email="524K0006@student.tdtu.edu.vn",
                    so_du=10000000.00
                ),
                UserModel(
                    mssv="524K0011",
                    ten_dang_nhap="phuc123",
                    mat_khau="123456",
                    ho_ten="Nguyễn Gia Phúc",
                    so_dien_thoai="0902222222",
                    email="524K0011@student.tdtu.edu.vn",
                    so_du=10000000.00
                ),
                UserModel(
                    mssv="523V0005",
                    ten_dang_nhap="nhi123",
                    mat_khau="123456",
                    ho_ten="Hồng Bảo Nhi",
                    so_dien_thoai="0903333333",
                    email="523V0005@student.tdtu.edu.vn",
                    so_du=10000000.00
                ),
                UserModel(
                    mssv="524V0007",
                    ten_dang_nhap="nhu123",
                    mat_khau="123456",
                    ho_ten="Phan Nguyễn Thảo Như",
                    so_dien_thoai="0904444444",
                    email="524V0007@student.tdtu.edu.vn",
                    so_du=10000000.00
                ),
            ])
            db.commit()
    except Exception:
        db.rollback()
    finally:
        db.close()

ensure_seed_users()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# 3. FastAPI Initialization & CORS
app = FastAPI(
    title="Auth & User Service - TDTU iBanking",
    description="Microservice quản lý xác thực người dùng, thông tin cá nhân và số dư tài khoản",
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
class LoginRequest(BaseModel):
    username: str = Field(..., min_length=1, description="Tên đăng nhập hoặc MSSV")
    password: str = Field(..., min_length=1, description="Mật khẩu")

class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    MaNguoiDung: int
    MSSV: str
    HoTen: str
    SoDienThoai: str
    Email: str
    SoDuKhaDung: float

class UserProfileResponse(BaseModel):
    MaNguoiDung: int
    MSSV: str
    username: str
    full_name: str
    HoTen: str
    phone: str
    SoDienThoai: str
    email: str
    Email: str
    available_balance: float
    SoDuKhaDung: float

class ValidateTokenResponse(BaseModel):
    valid: bool
    user_id: Optional[int] = None
    mssv: Optional[str] = None
    full_name: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    available_balance: Optional[float] = None

class DeductBalanceRequest(BaseModel):
    amount: float = Field(..., gt=0, description="Số tiền cần trừ (> 0)")

def get_student_email(user: UserModel) -> str:
    """Đảm bảo email của tài khoản luôn lấy theo <MSSV>@student.tdtu.edu.vn"""
    if user.mssv:
        return f"{user.mssv.upper()}@student.tdtu.edu.vn"
    return user.email

def extract_user_from_token(authorization: Optional[str], db: Session) -> Optional[UserModel]:
    if not authorization or not authorization.startswith("Bearer "):
        return None
    token = authorization.replace("Bearer ", "", 1).strip()
    if not token or not token.startswith("mock_jwt_token_"):
        return None
    try:
        parts = token.replace("mock_jwt_token_", "", 1).split("_")
        user_id = int(parts[0])
        return db.query(UserModel).filter(UserModel.ma_nguoi_dung == user_id).first()
    except (ValueError, IndexError):
        return None

def format_user_profile(user: UserModel) -> dict:
    balance = float(user.so_du)
    student_email = get_student_email(user)
    return {
        "MaNguoiDung": user.ma_nguoi_dung,
        "MSSV": user.mssv,
        "username": user.ten_dang_nhap,
        "full_name": user.ho_ten,
        "HoTen": user.ho_ten,
        "phone": user.so_dien_thoai,
        "SoDienThoai": user.so_dien_thoai,
        "email": student_email,
        "Email": student_email,
        "available_balance": balance,
        "SoDuKhaDung": balance
    }

# 5. API Endpoints

@app.post("/api/v1/auth/login", response_model=LoginResponse, tags=["Auth"])
def login(request: LoginRequest, db: Session = Depends(get_db)):
    """Đăng nhập tài khoản hệ thống bằng username (hoặc MSSV) và password"""
    login_input = request.username.strip()
    user = db.query(UserModel).filter(
        or_(
            UserModel.ten_dang_nhap == login_input,
            func.upper(UserModel.mssv) == login_input.upper()
        ),
        UserModel.mat_khau == request.password
    ).first()

    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Sai tên đăng nhập hoặc mật khẩu"
        )

    student_email = get_student_email(user)
    token = f"mock_jwt_token_{user.ma_nguoi_dung}_{user.ten_dang_nhap}"
    return {
        "access_token": token,
        "token_type": "bearer",
        "MaNguoiDung": user.ma_nguoi_dung,
        "MSSV": user.mssv,
        "HoTen": user.ho_ten,
        "SoDienThoai": user.so_dien_thoai,
        "Email": student_email,
        "SoDuKhaDung": float(user.so_du)
    }

@app.get("/api/v1/auth/validate", response_model=ValidateTokenResponse, tags=["Auth"])
def validate_token(
    authorization: Optional[str] = Header(default=None, alias="Authorization"),
    db: Session = Depends(get_db)
):
    """Xác thực Bearer Token và trả về thông tin người dùng hiện tại"""
    user = extract_user_from_token(authorization, db)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token không hợp lệ hoặc đã hết phiên đăng nhập"
        )

    return {
        "valid": True,
        "user_id": user.ma_nguoi_dung,
        "mssv": user.mssv,
        "full_name": user.ho_ten,
        "phone": user.so_dien_thoai,
        "email": get_student_email(user),
        "available_balance": float(user.so_du)
    }

@app.get("/api/v1/users/me", response_model=UserProfileResponse, tags=["User"])
def get_my_profile(
    authorization: Optional[str] = Header(default=None, alias="Authorization"),
    db: Session = Depends(get_db)
):
    """Lấy thông tin tài khoản người dùng đang đăng nhập từ Bearer Token"""
    user = extract_user_from_token(authorization, db)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Vui lòng đăng nhập để truy cập thông tin tài khoản"
        )

    return format_user_profile(user)

@app.get("/api/v1/users/{user_id}", response_model=UserProfileResponse, tags=["User Internal"])
def get_user_by_id(user_id: int, db: Session = Depends(get_db)):
    """API nội bộ: Lấy thông tin người dùng theo ID (Bao gồm MSSV, Họ tên, SĐT, Email @student.tdtu.edu.vn, Số dư)"""
    user = db.query(UserModel).filter(UserModel.ma_nguoi_dung == user_id).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Không tìm thấy người dùng"
        )

    return format_user_profile(user)

@app.post("/api/v1/users/{user_id}/deduct-balance", tags=["User Internal"])
def deduct_balance(user_id: int, request: DeductBalanceRequest, db: Session = Depends(get_db)):
    """
    API nội bộ: Được gọi bởi Payment Service để trừ số dư tài khoản.
    Áp dụng Pessimistic Locking (SELECT ... FOR UPDATE) để chống âm số dư khi có nhiều giao dịch đồng thời.
    """
    try:
        user = (
            db.query(UserModel)
            .filter(UserModel.ma_nguoi_dung == user_id)
            .with_for_update()
            .first()
        )
        if not user:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Người dùng không tồn tại")

        current_balance = float(user.so_du)
        if current_balance < request.amount:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Số dư khả dụng không đủ để thực hiện giao dịch"
            )

        user.so_du = current_balance - request.amount
        db.commit()
        db.refresh(user)

        return {
            "status": "SUCCESS",
            "MaNguoiDung": user_id,
            "new_balance": float(user.so_du)
        }
    except HTTPException:
        db.rollback()
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Lỗi khi trừ số dư: {str(e)}"
        )
