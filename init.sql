CREATE TABLE IF NOT EXISTS "NguoiDung" (
    "MaNguoiDung" SERIAL PRIMARY KEY,
    "TenDangNhap" VARCHAR(50) UNIQUE NOT NULL,
    "MatKhau" VARCHAR(255) NOT NULL,
    "HoTen" VARCHAR(100) NOT NULL,
    "Email" VARCHAR(100) UNIQUE NOT NULL,
    "SoDuKhaDung" NUMERIC(15, 2) NOT NULL CHECK ("SoDuKhaDung" >= 0)
);

CREATE TABLE IF NOT EXISTS "SinhVien" (
    "MSSV" VARCHAR(20) PRIMARY KEY,
    "HoTen" VARCHAR(100) NOT NULL,
    "Email" VARCHAR(100),
    "SoDienThoai" VARCHAR(20)
);

CREATE TABLE IF NOT EXISTS "HocPhi" (
    "MaHocPhi" SERIAL PRIMARY KEY,
    "MSSV" VARCHAR(20) REFERENCES "SinhVien"("MSSV"),
    "HocKy" VARCHAR(50) NOT NULL,
    "SoTienPhaiNop" NUMERIC(15, 2) NOT NULL CHECK ("SoTienPhaiNop" >= 0),
    "TrangThai" VARCHAR(30) NOT NULL
);

CREATE TABLE IF NOT EXISTS "GiaoDich" (
    "MaGiaoDich" VARCHAR(50) PRIMARY KEY,
    "MaNguoiDung" INT REFERENCES "NguoiDung"("MaNguoiDung"),
    "MaHocPhi" INT REFERENCES "HocPhi"("MaHocPhi"),
    "SoTienGiaoDich" NUMERIC(15, 2) NOT NULL,
    "NgayGiaoDich" TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    "TrangThai" VARCHAR(30) NOT NULL
);

CREATE TABLE IF NOT EXISTS "XacThucOTP" (
    "MaOTP" SERIAL PRIMARY KEY,
    "MaGiaoDich" VARCHAR(50) REFERENCES "GiaoDich"("MaGiaoDich"),
    "MaCode" VARCHAR(10) NOT NULL,
    "ThoiGianTao" TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    "ThoiGianHetHan" TIMESTAMP NOT NULL,
    "TrangThai" VARCHAR(30) NOT NULL
);

INSERT INTO "NguoiDung" ("TenDangNhap", "MatKhau", "HoTen", "Email", "SoDuKhaDung") VALUES
('khiem123', '123456', 'Thân Vũ Gia Khiêm', 'khiem@gmail.com', 5000000.00),
('phuc123',  '123456', 'Nguyễn Gia Phúc',   'giaphuc@gmail.com', 5000000.00),
('nhi123',   '123456', 'Hồng Bảo Nhi',      'nhi@gmail.com',     5000000.00);

INSERT INTO "SinhVien" ("MSSV", "HoTen") VALUES
('524K0006', 'Thân Vũ Gia Khiêm'),
('524K0001', 'Nguyễn Gia Phúc'),
('524K0005', 'Hồng Bảo Nhi');

INSERT INTO "HocPhi" ("MSSV", "HocKy", "SoTienPhaiNop", "TrangThai") VALUES
('524K0006', 'HK1-2026', 8500000.00,  'DA_DONG'),
('524K0001', 'HK1-2026', 750000.00,   'CHUA_DONG'),
('524K0005', 'HK1-2026', 15000000.00, 'CHUA_DONG');