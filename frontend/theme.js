// Apply the saved theme before the stylesheet paints, including on login.
(() => {
    const storageKey = 'tdtu-theme';
    const root = document.documentElement;
    let savedTheme;
    try { savedTheme = localStorage.getItem(storageKey); } catch { /* Storage can be disabled. */ }
    root.dataset.theme = savedTheme === 'dark' ? 'dark' : 'light';

    function updateControls() {
        const dark = root.dataset.theme === 'dark';
        const label = dark ? 'Chuyển sang chế độ sáng' : 'Chuyển sang chế độ tối';
        document.querySelectorAll('[data-theme-toggle]').forEach(button => {
            button.setAttribute('aria-pressed', String(dark));
            button.setAttribute('aria-label', label);
            button.title = label;
            button.querySelector('[data-theme-label]').textContent = dark ? 'Chế độ sáng' : 'Chế độ tối';
        });
    }

    function toggle() {
        const theme = root.dataset.theme === 'dark' ? 'light' : 'dark';
        root.dataset.theme = theme;
        try { localStorage.setItem(storageKey, theme); } catch { /* Switching still works without storage. */ }
        updateControls();
    }

    document.addEventListener('click', event => {
        if (event.target.closest('[data-theme-toggle]')) toggle();
    });
    window.iBankingTheme = { updateControls };
})();
