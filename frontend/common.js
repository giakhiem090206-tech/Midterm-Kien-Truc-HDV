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

// Chặn truy cập khi chưa đăng nhập và đồng bộ tên người dùng lên app shell.
function requireLogin() {
    if (!getToken()) {
        window.location.href = 'login.html';
        return false;
    }
    const userName = sessionStorage.getItem('HoTen') || '';
    document.querySelectorAll('#nav-user-name, [data-user-name]').forEach(el => {
        el.innerText = userName;
    });
    return true;
}

function mountAppShell() {
    const page = document.body.dataset.appPage;
    if (!page) return;

    const container = document.querySelector('.page-container');
    if (!container) return;

    const titles = {
        dashboard: ['TDTU iBanking', 'Quản lý việc đóng học phí an toàn và đơn giản.'],
        tuition: ['Thanh toán học phí', 'Tra cứu và thanh toán học phí của sinh viên TDTU an toàn, nhanh chóng.'],
        review: ['Kiểm tra giao dịch', 'Vui lòng kiểm tra kỹ thông tin trước khi xác thực.'],
        payment: ['Xác thực OTP', 'Bước bảo vệ cuối cùng trước khi hệ thống thực hiện thanh toán.'],
        history: ['Lịch sử giao dịch', 'Theo dõi các giao dịch thanh toán học phí của bạn.'],
        profile: ['Thông tin tài khoản', 'Thông tin bảo mật được đồng bộ từ tài khoản đã đăng nhập.']
    };
    const [title, subtitle] = titles[page] || titles.tuition;
    const activePage = ['payment', 'review'].includes(page) ? 'tuition' : page;
    const shell = document.createElement('div');
    shell.className = 'app-shell';
    shell.innerHTML = `
        <aside class="app-sidebar">
            <div class="brand"><span class="brand-mark" aria-hidden="true">◈</span><span>TDTU<small>TDTU iBanking</small></span></div>
            <nav class="app-nav" aria-label="Điều hướng chính">
                <a class="${activePage === 'dashboard' ? 'active' : ''}" href="dashboard.html"><span class="nav-icon">▣</span><span>Tổng quan</span></a>
                <a class="${activePage === 'tuition' ? 'active' : ''}" href="tuition.html"><span class="nav-icon">☷</span><span>Đóng học phí</span></a>
                <a class="${activePage === 'history' ? 'active' : ''}" href="history.html"><span class="nav-icon">◷</span><span>Lịch sử giao dịch</span></a>
                <a class="${activePage === 'profile' ? 'active' : ''}" href="profile.html"><span class="nav-icon">●</span><span>Tài khoản</span></a>
            </nav>
            <div class="sidebar-bottom"><a href="#" data-logout>Đăng xuất ↗</a></div>
        </aside>
        <main class="app-main">
            <header class="app-header">
                <div class="page-heading"><div class="eyebrow">TDTU iBanking</div><h1>${title}</h1><p>${subtitle}</p></div>
                <div class="header-actions"><a class="help-link" href="#" aria-label="Trợ giúp">Trợ giúp</a><div class="user-chip"><span class="avatar" aria-hidden="true">●</span><span data-user-name></span></div></div>
            </header>
        </main>`;

    const oldNavbar = document.querySelector('.navbar');
    if (oldNavbar) oldNavbar.remove();
    container.classList.add('app-page-container');
    shell.querySelector('.app-main').appendChild(container);
    document.body.insertBefore(shell, document.body.firstChild);
    shell.querySelector('[data-logout]').addEventListener('click', event => {
        event.preventDefault();
        logout();
    });
    const userName = sessionStorage.getItem('HoTen') || '';
    shell.querySelectorAll('[data-user-name]').forEach(el => { el.innerText = userName; });
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

mountAppShell();
