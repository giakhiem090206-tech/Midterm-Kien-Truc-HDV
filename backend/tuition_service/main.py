import os
from typing import List
from fastapi import FastAPI, Depends, HTTPException, status, Path
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sqlalchemy import Column, Integer, String, Numeric, create_engine, func
from sqlalchemy.orm import declarative_base, Session, sessionmaker

# 1. Cấu hình Database
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://root:rootpassword@db:5432/ibanking")
engine = create_engine(DATABASE_URL, pool_pre_ping=True)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# 2. Database Model "hoc_phi" (đồng bộ 100% với init.sql)
class HocPhiModel(Base):
    __tablename__ = "hoc_phi"
    ma_hoc_phi = Column(Integer, primary_key=True, index=True)
    mssv = Column(String(20), unique=True, nullable=False, index=True)
    ho_ten_sinh_vien = Column(String(100), nullable=False)
    hoc_ky = Column(String(50), nullable=False)
    so_tien_phai_nop = Column(Numeric(15, 2), nullable=False)
    trang_thai = Column(String(30), nullable=False, default="CHUA_DONG")

Base.metadata.create_all(bind=engine)

def ensure_seed_tuitions():
    db = SessionLocal()
    try:
        if db.query(HocPhiModel).count() == 0:
            db.add_all([
                HocPhiModel(mssv="524K0011", ho_ten_sinh_vien="Nguyễn Gia Phúc", hoc_ky="HK1-2026-2027", so_tien_phai_nop=5300000.00, trang_thai="CHUA_DONG"),
                HocPhiModel(mssv="523V0005", ho_ten_sinh_vien="Hồng Bảo Nhi", hoc_ky="HK1-2026-2027", so_tien_phai_nop=5300000.00, trang_thai="CHUA_DONG"),
                HocPhiModel(mssv="524K0006", ho_ten_sinh_vien="Thân Vũ Gia Khiêm", hoc_ky="HK1-2026-2027", so_tien_phai_nop=5300000.00, trang_thai="DA_DONG"),
                HocPhiModel(mssv="524V0007", ho_ten_sinh_vien="Phan Nguyễn Thảo Như", hoc_ky="HK1-2026-2027", so_tien_phai_nop=5300000.00, trang_thai="CHUA_DONG"),
            ])
            db.commit()
    except Exception:
        db.rollback()
    finally:
        db.close()

ensure_seed_tuitions()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# 3. Khởi tạo FastAPI & CORS
app = FastAPI(
    title="Tuition Service - TDTU iBanking",
    description="Microservice quản lý thông tin sinh viên và tra cứu/gạch nợ học phí TDTU",
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
class TuitionDetailResponse(BaseModel):
    MaHocPhi: int
    MSSV: str
    HoTen: str
    HocKy: str
    SoTienPhaiNop: float
    TrangThai: str

def format_tuition(hp: HocPhiModel) -> dict:
    return {
        "MaHocPhi": hp.ma_hoc_phi,
        "MSSV": hp.mssv,
        "HoTen": hp.ho_ten_sinh_vien,
        "HocKy": hp.hoc_ky,
        "SoTienPhaiNop": float(hp.so_tien_phai_nop),
        "TrangThai": hp.trang_thai
    }

# 5. API Endpoints

@app.get("/api/v1/tuitions", response_model=List[TuitionDetailResponse], tags=["Tuition Public"])
def list_all_tuitions(db: Session = Depends(get_db)):
    """Lấy danh sách toàn bộ học phí sinh viên (hỗ trợ kiểm tra nhanh dữ liệu)"""
    records = db.query(HocPhiModel).order_by(HocPhiModel.mssv.asc()).all()
    return [format_tuition(hp) for hp in records]

@app.get("/api/v1/tuitions/{mssv}", response_model=TuitionDetailResponse, tags=["Tuition Public"])
def lookup_tuition(
    mssv: str = Path(..., title="Mã số sinh viên"),
    db: Session = Depends(get_db)
):
    """
    Tra cứu thông tin sinh viên và khoản học phí theo MSSV.
    Trả về 404 Not Found nếu không tìm thấy MSSV.
    """
    clean_mssv = mssv.strip().upper()
    hp = db.query(HocPhiModel).filter(func.upper(HocPhiModel.mssv) == clean_mssv).first()

    if not hp:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Không tìm thấy sinh viên với MSSV '{clean_mssv}'"
        )

    return format_tuition(hp)

@app.get("/api/v1/tuitions/detail/{ma_hoc_phi}", response_model=TuitionDetailResponse, tags=["Tuition Internal"])
def get_tuition_by_id(ma_hoc_phi: int, db: Session = Depends(get_db)):
    """
    API nội bộ: Lấy chi tiết khoản học phí theo MaHocPhi (Cho Payment Service gọi)
    """
    hp = db.query(HocPhiModel).filter(HocPhiModel.ma_hoc_phi == ma_hoc_phi).first()
    if not hp:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Không tìm thấy khoản học phí"
        )

    return format_tuition(hp)

@app.post("/api/v1/tuitions/{ma_hoc_phi}/pay", tags=["Tuition Internal"])
def mark_tuition_as_paid(ma_hoc_phi: int, db: Session = Depends(get_db)):
    """
    API nội bộ: Được gọi bởi Payment Service để cập nhật gạch nợ học phí sang DA_DONG.
    Áp dụng Pessimistic Locking (SELECT ... FOR UPDATE) để chống thanh toán trùng khi có nhiều request đồng thời.
    """
    try:
        hp = (
            db.query(HocPhiModel)
            .filter(HocPhiModel.ma_hoc_phi == ma_hoc_phi)
            .with_for_update()
            .first()
        )
        if not hp:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Khoản học phí không tồn tại"
            )

        if hp.trang_thai == "DA_DONG":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Khoản học phí này đã được đóng trước đó"
            )

        hp.trang_thai = "DA_DONG"
        db.commit()
        db.refresh(hp)

        return {
            "status": "SUCCESS",
            "MaHocPhi": ma_hoc_phi,
            "MSSV": hp.mssv,
            "TrangThai": hp.trang_thai,
            "message": "Đã gạch nợ học phí thành công"
        }
    except HTTPException:
        db.rollback()
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Lỗi khi gạch nợ học phí: {str(e)}"
        )
