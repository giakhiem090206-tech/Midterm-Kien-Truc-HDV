-- 1. BẢNG NGƯỜI DÙNG (Quản lý User, số dư & thông tin cá nhân)
CREATE TABLE IF NOT EXISTS nguoi_dung (
    ma_nguoi_dung SERIAL PRIMARY KEY,
    ten_dang_nhap VARCHAR(50) UNIQUE NOT NULL,
    mat_khau VARCHAR(255) NOT NULL,
    ho_ten VARCHAR(100) NOT NULL,
    so_dien_thoai VARCHAR(20) NOT NULL,
    email VARCHAR(100) UNIQUE NOT NULL,
    so_du NUMERIC(15, 2) NOT NULL CHECK (so_du >= 0)
);

-- 2. BẢNG HỌC PHÍ (Quản lý thông tin nợ học phí sinh viên TDTU)
CREATE TABLE IF NOT EXISTS hoc_phi (
    ma_hoc_phi SERIAL PRIMARY KEY,
    mssv VARCHAR(20) NOT NULL,
    ho_ten_sinh_vien VARCHAR(100) NOT NULL,
    hoc_ky VARCHAR(50) NOT NULL,
    so_tien_phai_nop NUMERIC(15, 2) NOT NULL CHECK (so_tien_phai_nop >= 0),
    trang_thai VARCHAR(30) NOT NULL DEFAULT 'CHUA_DONG' -- CHUA_DONG, DANG_XU_LY, DA_DONG
);

-- 3. BẢNG GIAO DỊCH (Lịch sử thanh toán & Trạng thái ACID)
CREATE TABLE IF NOT EXISTS giao_dich (
    ma_giao_dich VARCHAR(50) PRIMARY KEY,
    ma_nguoi_dung INT NOT NULL REFERENCES nguoi_dung(ma_nguoi_dung),
    ma_hoc_phi INT NOT NULL REFERENCES hoc_phi(ma_hoc_phi),
    so_tien_giao_dich NUMERIC(15, 2) NOT NULL,
    thoi_gian_tao TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    trang_thai VARCHAR(30) NOT NULL -- PENDING, SUCCESS, FAILED
);

-- 4. BẢNG XÁC THỰC OTP (OTP 5 phút, dùng 1 lần)
CREATE TABLE IF NOT EXISTS xac_thuc_otp (
    ma_otp SERIAL PRIMARY KEY,
    ma_giao_dich VARCHAR(50) NOT NULL REFERENCES giao_dich(ma_giao_dich) ON DELETE CASCADE,
    ma_code VARCHAR(10) NOT NULL,
    thoi_gian_tao TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    thoi_gian_het_han TIMESTAMP NOT NULL,
    trang_thai VARCHAR(30) NOT NULL DEFAULT 'CHUA_SU_DUNG' -- CHUA_SU_DUNG, DA_SU_DUNG, HET_HAN
);

-- -------------------------------------------------------------
-- DỮ LIỆU MẪU (MOCK DATA CỦA 3 THÀNH VIÊN)
-- -------------------------------------------------------------

INSERT INTO nguoi_dung (ten_dang_nhap, mat_khau, ho_ten, so_dien_thoai, email, so_du) VALUES
('khiem123', '123456', 'Thân Vũ Gia Khiêm', '0901111111', 'khiem@gmail.com', 5000000.00),
('phuc123',  '123456', 'Nguyễn Gia Phúc',   '0902222222', 'giaphuc@gmail.com', 5000000.00),
('nhi123',   '123456', 'Hồng Bảo Nhi',      '0903333333', 'nhi@gmail.com',     5000000.00)
ON CONFLICT (ten_dang_nhap) DO NOTHING;

INSERT INTO hoc_phi (mssv, ho_ten_sinh_vien, hoc_ky, so_tien_phai_nop, trang_thai) VALUES
('524K0006', 'Thân Vũ Gia Khiêm', 'HK1-2026', 8500000.00,  'DA_DONG'),
('524K0001', 'Nguyễn Gia Phúc',   'HK1-2026', 750000.00,   'CHUA_DONG'),
('524K0005', 'Hồng Bảo Nhi',      'HK1-2026', 15000000.00, 'CHUA_DONG')
ON CONFLICT DO NOTHING;