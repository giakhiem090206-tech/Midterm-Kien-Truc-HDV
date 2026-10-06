import os
from fastapi import FastAPI, Depends, HTTPException, status, Path
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

# 2. Database Models
class SinhVienModel(Base):
    __tablename__ = "SinhVien"
    MSSV = Column(String(20), primary_key=True)
    HoTen = Column(String(100), nullable=False)
    Email = Column(String(100))
    SoDienThoai = Column(String(20))

class HocPhiModel(Base):
    __tablename__ = "HocPhi"
    MaHocPhi = Column(Integer, primary_key=True, index=True)
    MSSV = Column(String(20), nullable=False)
    HocKy = Column(String(50), nullable=False)
    SoTienPhaiNop = Column(Numeric(15, 2), nullable=False)
    TrangThai = Column(String(30), nullable=False)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# 3. Khởi tạo FastAPI & CORS
app = FastAPI(title="Tuition Service", version="1.0.0")

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

# 5. API Endpoints

@app.get("/api/v1/tuitions/{mssv}", response_model=TuitionDetailResponse, tags=["Tuition Public"])
def lookup_tuition(
    mssv: str = Path(..., title="Mã số sinh viên"),
    db: Session = Depends(get_db)
):
    """
    Tra cứu khoản học phí CHƯA_ĐÓNG của sinh viên theo MSSV (Dành cho Frontend)
    """
    sv = db.query(SinhVienModel).filter(SinhVienModel.MSSV == mssv).first()
    if not sv:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Không tìm thấy sinh viên"
        )

    # Tìm khoản học phí chưa đóng
    hp = db.query(HocPhiModel).filter(
        HocPhiModel.MSSV == mssv,
        HocPhiModel.TrangThai == "CHUA_DONG"
    ).first()

    if not hp:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Sinh viên không có khoản học phí cần nộp hoặc đã đóng đủ"
        )

    return {
        "MaHocPhi": hp.MaHocPhi,
        "MSSV": sv.MSSV,
        "HoTen": sv.HoTen,
        "HocKy": hp.HocKy,
        "SoTienPhaiNop": float(hp.SoTienPhaiNop),
        "TrangThai": hp.TrangThai
    }

@app.get("/api/v1/tuitions/detail/{ma_hoc_phi}", response_model=TuitionDetailResponse, tags=["Tuition Internal"])
def get_tuition_by_id(ma_hoc_phi: int, db: Session = Depends(get_db)):
    """
    API nội bộ: Lấy chi tiết khoản học phí theo MaHocPhi (Cho Payment Service gọi)
    """
    hp = db.query(HocPhiModel).filter(HocPhiModel.MaHocPhi == ma_hoc_phi).first()
    if not hp:
        raise HTTPException(status_code=404, detail="Không tìm thấy khoản học phí")

    sv = db.query(SinhVienModel).filter(SinhVienModel.MSSV == hp.MSSV).first()
    
    return {
        "MaHocPhi": hp.MaHocPhi,
        "MSSV": hp.MSSV,
        "HoTen": sv.HoTen if sv else "",
        "HocKy": hp.HocKy,
        "SoTienPhaiNop": float(hp.SoTienPhaiNop),
        "TrangThai": hp.TrangThai
    }

@app.post("/api/v1/tuitions/{ma_hoc_phi}/pay", tags=["Tuition Internal"])
def mark_tuition_as_paid(ma_hoc_phi: int, db: Session = Depends(get_db)):
    """
    API nội bộ: Được gọi bởi Payment Service để cập nhật gạch nợ học phí sang DA_DONG
    """
    hp = db.query(HocPhiModel).filter(HocPhiModel.MaHocPhi == ma_hoc_phi).first()
    if not hp:
        raise HTTPException(status_code=404, detail="Khoản học phí không tồn tại")
    
    if hp.TrangThai == "DA_DONG":
        raise HTTPException(status_code=400, detail="Khoản học phí này đã được đóng trước đó")

    hp.TrangThai = "DA_DONG"
    db.commit()

    return {
        "status": "SUCCESS",
        "MaHocPhi": ma_hoc_phi,
        "message": "Đã gạch nợ học phí thành công"
    }