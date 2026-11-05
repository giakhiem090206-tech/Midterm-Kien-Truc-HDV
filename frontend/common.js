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

// Chỉ gán avatar cho các tài khoản demo đã biết; tài khoản khác dùng icon chung.
function userAvatarSrc(identity) {
    const profile = identity && typeof identity === 'object' ? identity : {};
    const studentId = String(profile.student_id || profile.MSSV || (profile.email || '').split('@')[0]).trim().toUpperCase();
    const avatarsByStudentId = {
        '523V0005': 'assets/user-female.svg',
        '524K0006': 'assets/user-male.svg',
        '524K0011': 'assets/user-male.svg',
    };
    if (Object.prototype.hasOwnProperty.call(avatarsByStudentId, studentId)) return avatarsByStudentId[studentId];
    const fullName = typeof identity === 'string' ? identity : profile.full_name || profile.HoTen;
    const name = String(fullName || '').normalize('NFD').replace(/[\u0300-\u036f]/g, '')
        .trim().toLowerCase().replace(/\s+/g, ' ');
    const avatars = {
        'hong bao nhi': 'assets/user-female.svg',
        'than vu gia khiem': 'assets/user-male.svg',
        'nguyen gia phuc': 'assets/user-male.svg',
    };
    return Object.prototype.hasOwnProperty.call(avatars, name) ? avatars[name] : 'assets/user.svg';
}

function syncAccountAvatars(fullName = sessionStorage.getItem('HoTen')) {
    const src = userAvatarSrc(fullName);
    document.querySelectorAll('[data-account-avatar]').forEach(img => {
        img.setAttribute('src', src);
    });
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
            <div class="brand"><span class="brand-mark" aria-hidden="true"><img src="assets/wallet.svg" alt="" width="28" height="28"></span><span>TDTU<small>TDTU iBanking</small></span></div>
            <nav class="app-nav" aria-label="Điều hướng chính">
                <a class="${activePage === 'dashboard' ? 'active' : ''}" href="dashboard.html"><span class="nav-icon">▣</span><span>Tổng quan</span></a>
                <a class="${activePage === 'tuition' ? 'active' : ''}" href="tuition.html"><span class="nav-icon">☷</span><span>Đóng học phí</span></a>
                <a class="${activePage === 'history' ? 'active' : ''}" href="history.html"><span class="nav-icon">◷</span><span>Lịch sử giao dịch</span></a>
                <a class="${activePage === 'profile' ? 'active' : ''}" href="profile.html"><span class="nav-icon nav-icon-user" aria-hidden="true"><img data-account-avatar src="assets/user.svg" alt="" width="18" height="18"></span><span>Tài khoản</span></a>
            </nav>
            <div class="sidebar-bottom"><a href="#" data-logout>Đăng xuất ↗</a></div>
        </aside>
        <main class="app-main">
            <header class="app-header">
                <div class="page-heading"><div class="eyebrow">TDTU iBanking</div><h1>${title}</h1><p>${subtitle}</p></div>
                <div class="header-actions">
                    <button type="button" class="theme-toggle" data-theme-toggle aria-pressed="false" aria-label="Chuyển sang chế độ tối" title="Chuyển sang chế độ tối">
                        <svg class="theme-icon theme-icon-moon" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M20.5 13.2A8.5 8.5 0 0 1 10.8 3.5 8.5 8.5 0 1 0 20.5 13.2Z"/></svg>
                        <svg class="theme-icon theme-icon-sun" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" aria-hidden="true"><circle cx="12" cy="12" r="4"/><path d="M12 2v2m0 16v2M2 12h2m16 0h2M5 5l1.5 1.5m11 11L19 19M5 19l1.5-1.5m11-11L19 5"/></svg>
                        <span data-theme-label>Chế độ tối</span>
                    </button>
                    <div class="user-chip"><span class="avatar" aria-hidden="true"><img data-account-avatar src="assets/user.svg" alt="" width="28" height="28"></span><span data-user-name></span></div>
                </div>
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
    syncAccountAvatars(userName);
    window.iBankingTheme?.updateControls();
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

