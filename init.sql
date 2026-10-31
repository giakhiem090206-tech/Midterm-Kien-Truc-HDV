-- =============================================================
-- CƠ SỞ DỮ LIỆU PHÂN HỆ ĐÓNG HỌC PHÍ TDTU IBANKING (PostgreSQL)
-- =============================================================

-- Xóa các bảng cũ (nếu có từ phiên bản trước) để tránh xung đột schema/constraint
DROP TABLE IF EXISTS xac_thuc_otp CASCADE;
DROP TABLE IF EXISTS giao_dich CASCADE;
DROP TABLE IF EXISTS hoc_phi CASCADE;
DROP TABLE IF EXISTS nguoi_dung CASCADE;
DROP TABLE IF EXISTS "XacThucOTP" CASCADE;
DROP TABLE IF EXISTS "GiaoDich" CASCADE;
DROP TABLE IF EXISTS "HocPhi" CASCADE;
DROP TABLE IF EXISTS "SinhVien" CASCADE;
DROP TABLE IF EXISTS "NguoiDung" CASCADE;

-- 1. BẢNG NGƯỜI DÙNG (Quản lý User, MSSV, số dư & thông tin cá nhân)
-- Email của tài khoản lấy theo định dạng <mssv>@student.tdtu.edu.vn
CREATE TABLE nguoi_dung (
    ma_nguoi_dung SERIAL PRIMARY KEY,
    mssv VARCHAR(20) UNIQUE NOT NULL,
    ten_dang_nhap VARCHAR(50) UNIQUE NOT NULL,
    mat_khau VARCHAR(255) NOT NULL,
    ho_ten VARCHAR(100) NOT NULL,
    so_dien_thoai VARCHAR(20) NOT NULL,
    email VARCHAR(100) UNIQUE NOT NULL,
    so_du NUMERIC(15, 2) NOT NULL CHECK (so_du >= 0)
);

-- 2. BẢNG HỌC PHÍ (Quản lý thông tin nợ học phí sinh viên TDTU)
CREATE TABLE hoc_phi (
    ma_hoc_phi SERIAL PRIMARY KEY,
    mssv VARCHAR(20) UNIQUE NOT NULL,
    ho_ten_sinh_vien VARCHAR(100) NOT NULL,
    hoc_ky VARCHAR(50) NOT NULL,
    so_tien_phai_nop NUMERIC(15, 2) NOT NULL CHECK (so_tien_phai_nop > 0),
    trang_thai VARCHAR(30) NOT NULL DEFAULT 'CHUA_DONG' CHECK (trang_thai IN ('CHUA_DONG', 'DANG_XU_LY', 'DA_DONG'))
);

-- 3. BẢNG GIAO DỊCH (Lịch sử thanh toán & Trạng thái ACID)
CREATE TABLE giao_dich (
    ma_giao_dich VARCHAR(50) PRIMARY KEY,
    ma_nguoi_dung INT NOT NULL REFERENCES nguoi_dung(ma_nguoi_dung),
    ma_hoc_phi INT NOT NULL REFERENCES hoc_phi(ma_hoc_phi),
    so_tien_giao_dich NUMERIC(15, 2) NOT NULL CHECK (so_tien_giao_dich > 0),
    thoi_gian_tao TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    trang_thai VARCHAR(30) NOT NULL CHECK (trang_thai IN ('PENDING', 'SUCCESS', 'FAILED'))
);

-- 4. BẢNG XÁC THỰC OTP (OTP gắn với giao dịch, hạn tối đa 5 phút, dùng 1 lần)
CREATE TABLE xac_thuc_otp (
    ma_otp SERIAL PRIMARY KEY,
    ma_giao_dich VARCHAR(50) NOT NULL REFERENCES giao_dich(ma_giao_dich) ON DELETE CASCADE,
    ma_code VARCHAR(10) NOT NULL,
    thoi_gian_tao TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    thoi_gian_het_han TIMESTAMP NOT NULL,
    trang_thai VARCHAR(30) NOT NULL DEFAULT 'CHUA_SU_DUNG' CHECK (trang_thai IN ('CHUA_SU_DUNG', 'DA_SU_DUNG', 'HET_HAN'))
);

-- -------------------------------------------------------------
-- DỮ LIỆU MẪU (MOCK DATA CỦA 3 THÀNH VIÊN & SINH VIÊN TDTU)
-- Email tài khoản được gắn tự động theo <MSSV>@student.tdtu.edu.vn
-- -------------------------------------------------------------

INSERT INTO nguoi_dung (mssv, ten_dang_nhap, mat_khau, ho_ten, so_dien_thoai, email, so_du) VALUES
('524K0006', 'khiem123', '123456', 'Thân Vũ Gia Khiêm', '0901111111', '524K0006@student.tdtu.edu.vn', 10000000.00),
('524K0011', 'phuc123',  '123456', 'Nguyễn Gia Phúc',   '0902222222', '524K0011@student.tdtu.edu.vn', 10000000.00),
('523V0005', 'nhi123',   '123456', 'Hồng Bảo Nhi',      '0903333333', '523V0005@student.tdtu.edu.vn',  10000000.00),
('524V0007', 'nhu123',  '123456', 'Phan Nguyễn Thảo Như',   '0904444444', '524V0007@student.tdtu.edu.vn', 10000000.00);


INSERT INTO hoc_phi (mssv, ho_ten_sinh_vien, hoc_ky, so_tien_phai_nop, trang_thai) VALUES
('524K0011', 'Nguyễn Gia Phúc',   'HK1-2026-2027',  5300000.00, 'CHUA_DONG'),
('523V0005', 'Hồng Bảo Nhi',      'HK1-2026-2027',  5300000.00, 'CHUA_DONG'),
('524K0006', 'Thân Vũ Gia Khiêm', 'HK1-2026-2027',  5300000.00, 'DA_DONG'),
('524V0007', 'Phan Nguyễn Thảo Như',    'HK1-2026-2027',  5300000.00, 'CHUA_DONG');
