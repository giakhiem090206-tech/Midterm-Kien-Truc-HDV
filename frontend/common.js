// Cấu hình & hàm dùng chung cho các trang
// Mọi API đi qua API Gateway (cùng địa chỉ với trang web). Gateway định tuyến theo đường dẫn:
// /auth, /users/me -> Auth Service; /tuitions -> Tuition Service; /payments -> Payment Service
const API_BASE = '/api/v1';

const STATUS_LABELS = {
    SUCCESS: 'Thành công',
    FAILED: 'Thất bại',
    PENDING: 'Chờ xác thực OTP',
    PROCESSING: 'Đang xử lý',
};

function getToken() {
    return sessionStorage.getItem('token');
}

function logout() {
    sessionStorage.clear();
    window.location.href = 'login.html';
}

// Chặn truy cập khi chưa đăng nhập, hiển thị tên người dùng trên navbar
function requireLogin() {
    if (!getToken()) {
        window.location.href = 'login.html';
        return false;
    }
    const nameEl = document.getElementById('nav-user-name');
    if (nameEl) nameEl.innerText = sessionStorage.getItem('HoTen') || '';
    return true;
}

// Gọi API backend: tự gắn JWT, chuyển lỗi backend thành Error(detail) để hiển thị lên UI
async function apiFetch(url, { method = 'GET', body, auth = true, headers: extraHeaders = {} } = {}) {
    const headers = { 'Content-Type': 'application/json', ...extraHeaders };
    if (auth) headers['Authorization'] = `Bearer ${getToken()}`;

    let res;
    try {
        res = await fetch(url, {
            method,
            headers,
            body: body !== undefined ? JSON.stringify(body) : undefined,
        });
    } catch (e) {
        throw new Error('Không kết nối được tới máy chủ, vui lòng thử lại!');
    }

    const data = await res.json().catch(() => ({}));

    if (res.status === 401 && auth) {
        sessionStorage.clear();
        alert(data.detail || 'Phiên đăng nhập đã hết hạn, vui lòng đăng nhập lại');
        window.location.href = 'login.html';
        throw new Error(data.detail);
    }

    if (!res.ok) {
        const err = new Error(typeof data.detail === 'string' ? data.detail : 'Đã có lỗi xảy ra, vui lòng thử lại!');
        err.status = res.status;
        throw err;
    }
    return data;
}

function formatVND(amount) {
    return Number(amount).toLocaleString('vi-VN') + ' VNĐ';
}

function escapeHtml(str) {
    return String(str ?? '').replace(/[&<>"']/g, c => ({
        '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
    }[c]));
}

function showAlert(el, text, type = 'error') {
    el.innerText = text;
    el.className = `alert alert-${type}`;
    el.style.display = 'block';
}

function hideAlert(el) {
    el.style.display = 'none';
}

// Khoá idempotency cho request tạo giao dịch: gửi lại cùng khoá thì backend trả lại giao dịch cũ
// (crypto.randomUUID chỉ có trên HTTPS/localhost nên tự sinh từ getRandomValues)
function newIdempotencyKey() {
    const bytes = crypto.getRandomValues(new Uint8Array(16));
    return Array.from(bytes, b => b.toString(16).padStart(2, '0')).join('');
}
