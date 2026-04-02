document.addEventListener('DOMContentLoaded', function () {
    const isTelegramBrowser = /Telegram/i.test(navigator.userAgent || '');
    if (isTelegramBrowser) {
        document.documentElement.classList.add('is-telegram-browser');
    }

    const toggle = document.getElementById('mobileMenuToggle');
    const overlay = document.getElementById('mobileMenuOverlay');
    const closeBtn = document.getElementById('mobileMenuClose');

    if (!toggle || !overlay || !closeBtn) return;

    function openMenu() {
        overlay.classList.add('mobile-menu-overlay--open');
        document.body.classList.add('no-scroll');
    }

    function closeMenu() {
        overlay.classList.remove('mobile-menu-overlay--open');
        document.body.classList.remove('no-scroll');
    }

    toggle.addEventListener('click', openMenu);
    closeBtn.addEventListener('click', closeMenu);

    // Закрыть по клику на затемнение
    overlay.addEventListener('click', function (e) {
        if (e.target === overlay) {
            closeMenu();
        }
    });

    // Закрыть по ESC
    document.addEventListener('keydown', function (e) {
        if (e.key === 'Escape') {
            closeMenu();
        }
    });
});
