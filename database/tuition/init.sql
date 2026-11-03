\connect tuition_db

CREATE TABLE IF NOT EXISTS "SinhVien" (
    "MSSV" VARCHAR(20) PRIMARY KEY,
    "HoTen" VARCHAR(100) NOT NULL,
    "Email" VARCHAR(100),
    "SoDienThoai" VARCHAR(20)
);

CREATE TABLE IF NOT EXISTS "HocPhi" (
    "MaHocPhi" SERIAL PRIMARY KEY,
    "MSSV" VARCHAR(20) NOT NULL REFERENCES "SinhVien"("MSSV"),
    "HocKy" VARCHAR(50) NOT NULL,
    "SoTienPhaiNop" NUMERIC(15, 2) NOT NULL CHECK ("SoTienPhaiNop" > 0),
    "TrangThai" VARCHAR(30) NOT NULL CHECK ("TrangThai" IN ('CHUA_DONG', 'DA_DONG')),
    "MaGiaoDichThanhToan" VARCHAR(50) UNIQUE
);

INSERT INTO "SinhVien" ("MSSV", "HoTen") VALUES
('524K0006', 'Thân Vũ Gia Khiêm'),
('524K0011', 'Nguyễn Gia Phúc'),
('523V0005', 'Hồng Bảo Nhi');

-- Dữ liệu dành cho kiểm thử số dư và race condition.
INSERT INTO "HocPhi" ("MSSV", "HocKy", "SoTienPhaiNop", "TrangThai") VALUES
('524K0006', 'HK1-2026', 50000000.00, 'DA_DONG'),
('524K0011', 'HK1-2026', 50000000.00, 'CHUA_DONG'),
('523V0005', 'HK1-2026', 50000000.00, 'CHUA_DONG');
