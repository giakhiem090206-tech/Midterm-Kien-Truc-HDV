-- Database-per-service: mỗi service sở hữu một database riêng,
-- các service chỉ giao tiếp với nhau qua REST API (không truy cập chéo bảng).
CREATE DATABASE auth_db;
CREATE DATABASE tuition_db;
CREATE DATABASE payment_db;

-- =====================================================================
-- AUTH SERVICE: người dùng & số dư
-- =====================================================================
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
('khiem123', '123456', 'Thân Vũ Gia Khiêm', '0901000006', '524k0006@student.tdtu.edu.vn', 5000000.00),
('phuc123',  '123456', 'Nguyễn Gia Phúc',   '0901000001', '524k0011@student.tdtu.edu.vn', 15500000.00),
('nhi123',   '123456', 'Hồng Bảo Nhi',      '0901000005', '523v0005@student.tdtu.edu.vn', 1000000.00);

-- =====================================================================
-- TUITION SERVICE: sinh viên & học phí
-- =====================================================================
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

-- Kịch bản test (reset DB bằng `docker compose down -v` giữa 2 kịch bản concurrency):
--  * 524K0006: đã đóng                                  -> tra cứu báo không còn khoản cần nộp
--  * 523V0005: nhi123 (1tr) trả 15tr                    -> số dư không đủ
--  * Concurrency #1: phuc123 (15.5tr) trả đồng thời 524K0011 (750k) + 523V0005 (15tr)
--                    -> tổng 15.75tr vượt số dư, chỉ 1 giao dịch thành công
--  * Concurrency #2: khiem123 và nhi123 cùng trả 524K0011 -> chỉ 1 giao dịch thành công
INSERT INTO "HocPhi" ("MSSV", "HocKy", "SoTienPhaiNop", "TrangThai") VALUES
('524K0006', 'HK1-2026', 8500000.00,  'DA_DONG'),
('524K0011', 'HK1-2026', 750000.00,   'CHUA_DONG'),
('523V0005', 'HK1-2026', 15000000.00, 'CHUA_DONG');

-- =====================================================================
-- PAYMENT SERVICE: giao dịch & OTP
-- MaNguoiDung / MaHocPhi tham chiếu sang service khác nên không đặt FK.
-- MSSV / TenSinhVien được lưu lại tại thời điểm giao dịch để hiển thị lịch sử.
-- =====================================================================
\connect payment_db

CREATE TABLE IF NOT EXISTS "GiaoDich" (
    "MaGiaoDich" VARCHAR(50) PRIMARY KEY,
    "MaNguoiDung" INT NOT NULL,
    "MaHocPhi" INT NOT NULL,
    "MSSV" VARCHAR(20) NOT NULL,
    "TenSinhVien" VARCHAR(100) NOT NULL,
    "SoTienGiaoDich" NUMERIC(15, 2) NOT NULL CHECK ("SoTienGiaoDich" > 0),
    "NgayGiaoDich" TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    "TrangThai" VARCHAR(30) NOT NULL CHECK ("TrangThai" IN ('PENDING', 'PROCESSING', 'SUCCESS', 'FAILED')),
    "UpdatedAt" TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    -- Khoá idempotency do client gửi khi tạo giao dịch: gửi lại cùng khoá không tạo giao dịch mới
    "IdempotencyKey" VARCHAR(100),
    CONSTRAINT "uq_giaodich_idempotency" UNIQUE ("MaNguoiDung", "IdempotencyKey")
);

CREATE TABLE IF NOT EXISTS "XacThucOTP" (
    "MaOTP" SERIAL PRIMARY KEY,
    "MaGiaoDich" VARCHAR(50) NOT NULL REFERENCES "GiaoDich"("MaGiaoDich"),
    "MaCode" VARCHAR(10) NOT NULL,
    "ThoiGianTao" TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    "ThoiGianHetHan" TIMESTAMP NOT NULL,
    "SoLanNhapSai" INT NOT NULL DEFAULT 0 CHECK ("SoLanNhapSai" >= 0),
    "TrangThai" VARCHAR(30) NOT NULL CHECK ("TrangThai" IN ('CHUA_SU_DUNG', 'DA_SU_DUNG'))
);
