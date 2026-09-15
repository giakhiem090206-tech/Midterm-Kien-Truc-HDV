CREATE TABLE IF NOT EXISTS nguoi_dung (
    ma_nguoi_dung SERIAL PRIMARY KEY,
    ten_dang_nhap VARCHAR(50) UNIQUE NOT NULL,
    mat_khau VARCHAR(255) NOT NULL,
    ho_ten VARCHAR(100) NOT NULL,
    email VARCHAR(100) UNIQUE NOT NULL,
    so_du_kha_dung NUMERIC(15, 2) NOT NULL CHECK (so_du_kha_dung >= 0)
);

CREATE TABLE IF NOT EXISTS sinh_vien (
    mssv VARCHAR(20) PRIMARY KEY,
    ho_ten VARCHAR(100) NOT NULL,
    email VARCHAR(100),
    so_dien_thoai VARCHAR(20)
);

CREATE TABLE IF NOT EXISTS hoc_phi (
    ma_hoc_phi SERIAL PRIMARY KEY,
    mssv VARCHAR(20) REFERENCES sinh_vien(mssv),
    hoc_ky VARCHAR(50) NOT NULL,
    so_tien_phai_nop NUMERIC(15, 2) NOT NULL CHECK (so_tien_phai_nop >= 0),
    trang_thai VARCHAR(30) NOT NULL
);

CREATE TABLE IF NOT EXISTS giao_dich (
    ma_giao_dich VARCHAR(50) PRIMARY KEY,
    ma_nguoi_dung INT REFERENCES nguoi_dung(ma_nguoi_dung),
    ma_hoc_phi INT REFERENCES hoc_phi(ma_hoc_phi),
    so_tien_giao_dich NUMERIC(15, 2) NOT NULL,
    ngay_giao_dich TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    trang_thai VARCHAR(30) NOT NULL
);

CREATE TABLE IF NOT EXISTS xac_thuc_otp (
    ma_otp SERIAL PRIMARY KEY,
    ma_giao_dich VARCHAR(50) REFERENCES giao_dich(ma_giao_dich),
    ma_code VARCHAR(10) NOT NULL,
    thoi_gian_tao TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    thoi_gian_het_han TIMESTAMP NOT NULL,
    trang_thai VARCHAR(30) NOT NULL
);

INSERT INTO nguoi_dung (ten_dang_nhap, mat_khau, ho_ten, email, so_du_kha_dung) VALUES
('khiem123', '123456', 'Thân Vũ Gia Khiêm', 'khiem@gmail.com', 5000000.00),
('phuc123',  '123456', 'Nguyễn Gia Phúc',   'giaphuc@gmail.com', 5000000.00),
('nhi123',   '123456', 'Hồng Bảo Nhi',      'nhi@gmail.com',     5000000.00);

INSERT INTO sinh_vien (mssv, ho_ten) VALUES
('524K0006', 'Thân Vũ Gia Khiêm'),
('524K0001', 'Nguyễn Gia Phúc'),
('524K0005', 'Hồng Bảo Nhi');

INSERT INTO hoc_phi (mssv, hoc_ky, so_tien_phai_nop, trang_thai) VALUES
('524K0006', 'HK1-2026', 8500000.00,  'DA_DONG'),
('524K0001', 'HK1-2026', 750000.00,   'CHUA_DONG'),
('524K0005', 'HK1-2026', 15000000.00, 'CHUA_DONG');
