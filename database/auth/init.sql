\connect auth_db

CREATE TABLE IF NOT EXISTS "NguoiDung" (
    "MaNguoiDung" SERIAL PRIMARY KEY,
    "TenDangNhap" VARCHAR(50) UNIQUE NOT NULL,
    "MatKhau" VARCHAR(255) NOT NULL,
    "HoTen" VARCHAR(100) NOT NULL,
    "SoDienThoai" VARCHAR(20) NOT NULL,
    "Email" VARCHAR(100) UNIQUE NOT NULL,
    "SoDuKhaDung" NUMERIC(15, 2) NOT NULL CHECK ("SoDuKhaDung" >= 0)
);

CREATE TABLE IF NOT EXISTS "BalanceOperation" (
    "MaOperation" SERIAL PRIMARY KEY,
    "MaGiaoDich" VARCHAR(50) NOT NULL,
    "Loai" VARCHAR(10) NOT NULL CHECK ("Loai" IN ('DEBIT', 'REFUND')),
    "SoTien" NUMERIC(15, 2) NOT NULL CHECK ("SoTien" > 0),
    "SoDuSau" NUMERIC(15, 2) NOT NULL CHECK ("SoDuSau" >= 0),
    "NgayTao" TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE ("MaGiaoDich", "Loai")
);

INSERT INTO "NguoiDung" ("TenDangNhap", "MatKhau", "HoTen", "SoDienThoai", "Email", "SoDuKhaDung") VALUES
('khiem123', '123456', 'Thân Vũ Gia Khiêm', '0903000001', '524k0006@student.tdtu.edu.vn', 60000000.00),
('phuc123',  '123456', 'Nguyễn Gia Phúc',   '0903000002', '524k0011@student.tdtu.edu.vn', 70000000.00),
('nhi123',   '123456', 'Hồng Bảo Nhi',      '0903000005', '523v0005@student.tdtu.edu.vn', 800000000.00);
