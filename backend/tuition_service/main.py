import os
from contextlib import asynccontextmanager
from fastapi import Depends, HTTPException, status, Path
from pydantic import BaseModel, Field
from sqlalchemy import Column, Integer, String, Numeric, create_engine, text
from sqlalchemy.orm import Session, declarative_base, sessionmaker
from security import get_current_user_id, verify_internal_key
from service_app import create_app

# 1. Cấu hình Database
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://root:rootpassword@db:5432/tuition_db")

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
    MaGiaoDichThanhToan = Column(String(50), unique=True, nullable=True)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# 3. Khởi tạo FastAPI
@asynccontextmanager
async def lifespan(app):
    # Migration cộng thêm cho DB tạo trước khi có khoá idempotency của saga
    with engine.begin() as connection:
        connection.execute(text(
            'ALTER TABLE "HocPhi" ADD COLUMN IF NOT EXISTS "MaGiaoDichThanhToan" VARCHAR(50)'
        ))
        connection.execute(text(
            'CREATE UNIQUE INDEX IF NOT EXISTS "uq_hocphi_payment_transaction" '
            'ON "HocPhi" ("MaGiaoDichThanhToan")'
        ))
    yield

app, logger = create_app("Tuition Service", "tuition-service", docs_prefix="/api/v1/tuitions", lifespan=lifespan)

# 4. Pydantic Schemas
class TuitionDetailResponse(BaseModel):
    MaHocPhi: int
    MSSV: str
    HoTen: str
    HocKy: str
    SoTienPhaiNop: float
    TrangThai: str

class MarkPaidResponse(BaseModel):
    status: str
    MaHocPhi: int
    message: str

class MarkPaidRequest(BaseModel):
    transaction_id: str = Field(min_length=1, max_length=50)

# 5. API Endpoints

@app.get("/api/v1/tuitions/{mssv}", response_model=TuitionDetailResponse, tags=["Tuition Public"],
         dependencies=[Depends(get_current_user_id)])
def lookup_tuition(
    mssv: str = Path(..., title="Mã số sinh viên", min_length=1, max_length=20),
    db: Session = Depends(get_db)
):
    """
    Tra cứu khoản học phí CHƯA_ĐÓNG của sinh viên theo MSSV (Dành cho Frontend, cần đăng nhập)
    """
    sv = db.query(SinhVienModel).filter(SinhVienModel.MSSV == mssv.strip().upper()).first()
    if not sv:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Không tìm thấy sinh viên"
        )

    # Tìm khoản học phí chưa đóng
    hp = db.query(HocPhiModel).filter(
        HocPhiModel.MSSV == sv.MSSV,
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

@app.get("/api/v1/tuitions/detail/{ma_hoc_phi}", response_model=TuitionDetailResponse, tags=["Tuition Internal"],
         dependencies=[Depends(verify_internal_key)])
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

@app.post("/api/v1/tuitions/{ma_hoc_phi}/pay", response_model=MarkPaidResponse, tags=["Tuition Internal"],
          dependencies=[Depends(verify_internal_key)])
def mark_tuition_as_paid(ma_hoc_phi: int, request: MarkPaidRequest, db: Session = Depends(get_db)):
    """
    API nội bộ: Được gọi bởi Payment Service để cập nhật gạch nợ học phí sang DA_DONG
    """
    # UPDATE có điều kiện (atomic): khi 2 request cùng gạch nợ 1 khoản, Postgres khoá dòng,
    # request sau chờ request trước commit rồi đánh giá lại WHERE -> 0 dòng được cập nhật
    updated = db.query(HocPhiModel).filter(
        HocPhiModel.MaHocPhi == ma_hoc_phi,
        HocPhiModel.TrangThai == "CHUA_DONG"
    ).update({
        HocPhiModel.TrangThai: "DA_DONG",
        HocPhiModel.MaGiaoDichThanhToan: request.transaction_id
    }, synchronize_session=False)
    db.commit()

    if updated == 0:
        hp = db.query(HocPhiModel).filter(HocPhiModel.MaHocPhi == ma_hoc_phi).first()
        if not hp:
            raise HTTPException(status_code=404, detail="Khoản học phí không tồn tại")
        if hp.TrangThai == "DA_DONG" and hp.MaGiaoDichThanhToan == request.transaction_id:
            logger.info("Giao dịch %s đã gạch nợ MaHocPhi=%s trước đó (idempotent)", request.transaction_id, ma_hoc_phi)
            return {
                "status": "SUCCESS",
                "MaHocPhi": ma_hoc_phi,
                "message": "Khoản học phí đã được ghi nhận cho giao dịch này"
            }
        logger.warning("Giao dịch %s bị từ chối: MaHocPhi=%s đã được giao dịch %s thanh toán",
                       request.transaction_id, ma_hoc_phi, hp.MaGiaoDichThanhToan)
        raise HTTPException(status_code=409, detail="Khoản học phí này đã được thanh toán trước đó")

    logger.info("Giao dịch %s: gạch nợ MaHocPhi=%s", request.transaction_id, ma_hoc_phi)
    return {
        "status": "SUCCESS",
        "MaHocPhi": ma_hoc_phi,
        "message": "Đã gạch nợ học phí thành công"
    }
