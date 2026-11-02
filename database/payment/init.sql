\connect payment_db

CREATE TABLE IF NOT EXISTS "GiaoDich" (
    "MaGiaoDich" VARCHAR(50) PRIMARY KEY,
    "MaNguoiDung" INT NOT NULL,
    "MaHocPhi" INT NOT NULL,
    "MSSV" VARCHAR(20) NOT NULL,
    "TenSinhVien" VARCHAR(100) NOT NULL,
    "SoTienGiaoDich" NUMERIC(15, 2) NOT NULL CHECK ("SoTienGiaoDich" > 0),
    "NgayGiaoDich" TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "TrangThai" VARCHAR(30) NOT NULL CHECK ("TrangThai" IN ('PENDING', 'PROCESSING', 'SUCCESS', 'FAILED')),
    "UpdatedAt" TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "IdempotencyKey" VARCHAR(100),
    CONSTRAINT "uq_giaodich_idempotency" UNIQUE ("MaNguoiDung", "IdempotencyKey")
);

CREATE TABLE IF NOT EXISTS "XacThucOTP" (
    "MaOTP" SERIAL PRIMARY KEY,
    "MaGiaoDich" VARCHAR(50) NOT NULL REFERENCES "GiaoDich"("MaGiaoDich"),
    "MaCode" VARCHAR(10) NOT NULL,
    "ThoiGianTao" TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "ThoiGianHetHan" TIMESTAMP NOT NULL,
    "SoLanNhapSai" INT NOT NULL DEFAULT 0 CHECK ("SoLanNhapSai" >= 0),
    "TrangThai" VARCHAR(30) NOT NULL CHECK ("TrangThai" IN ('CHUA_SU_DUNG', 'DA_SU_DUNG'))
);
