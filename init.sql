CREATE TABLE IF NOT EXISTS "NguoiDung" (
    "MaNguoiDung" SERIAL PRIMARY KEY,
    "TenDangNhap" VARCHAR(50) UNIQUE NOT NULL,
    "MatKhau" VARCHAR(255) NOT NULL,
    "HoTen" VARCHAR(100) NOT NULL,
    "Email" VARCHAR(100) NOT NULL,
    "SoDuKhaDung" NUMERIC(15, 2) NOT NULL
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
    "SoTienPhaiNop" NUMERIC(15, 2) NOT NULL,
    "TrangThai" VARCHAR(30) NOT NULL
);

CREATE TABLE IF NOT EXISTS "GiaoDich" (
    "MaGiaoDich" VARCHAR(50) PRIMARY KEY,
    "MaNguoiDung" INT REFERENCES "NguoiDung"("MaNguoiDung"),
    "MaHocPhi" INT REFERENCES "HocPhi"("MaHocPhi"),
    "SoTienGiaoDich" NUMERIC(15, 2) NOT NULL,
    "NgayGiaoDich" TIMESTAMP NOT NULL,
    "TrangThai" VARCHAR(30) NOT NULL
);

CREATE TABLE IF NOT EXISTS "XacThucOTP" (
    "MaOTP" SERIAL PRIMARY KEY,
    "MaGiaoDich" VARCHAR(50) REFERENCES "GiaoDich"("MaGiaoDich"),
    "MaCode" VARCHAR(10) NOT NULL,
    "ThoiGianTao" TIMESTAMP NOT NULL,
    "ThoiGianHetHan" TIMESTAMP NOT NULL,
    "TrangThai" VARCHAR(30) NOT NULL
);

INSERT INTO "NguoiDung" ("TenDangNhap", "MatKhau", "HoTen", "Email", "SoDuKhaDung")
VALUES ('phuc123', '123456', 'Gia Phúc', 'giaphuc@gmail.com', 2000000.00);

INSERT INTO "SinhVien" ("MSSV", "HoTen")
VALUES ('52100001', 'Gia Phúc');

INSERT INTO "HocPhi" ("MSSV", "HocKy", "SoTienPhaiNop", "TrangThai")
VALUES ('52100001', 'HK1-2026', 750000.00, 'CHUA_DONG');