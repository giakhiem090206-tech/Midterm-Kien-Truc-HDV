/**
 * CẤU HÌNH TẬP TRUNG FRONTEND (Config -> Feeding -> Placeholders -> UI)
 * Tránh hardcode các endpoint và thông số rải rác trên từng màn hình HTML.
 */
window.IBANKING_CONFIG = {
    SERVICES: {
        AUTH_URL: "http://localhost:8001",
        TUITION_URL: "http://localhost:8002",
        PAYMENT_URL: "http://localhost:8003"
    },
    PLACEHOLDERS: {
        USERNAME: "Nhập tên đăng nhập hoặc MSSV",
        MSSV: "Nhập mã số sinh viên cần tra cứu",
        GMAIL: "Nhập địa chỉ Gmail nhận mã OTP",
        OTP: "••••••"
    },
    generateIdempotencyKey: function(prefix) {
        return `${prefix}_${Date.now()}_${Math.random().toString(36).substring(2, 10)}`;
    }
};
