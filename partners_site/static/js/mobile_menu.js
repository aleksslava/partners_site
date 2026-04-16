document.addEventListener('DOMContentLoaded', function () {
    const ua = navigator.userAgent || '';
    const telegramObject = window.Telegram || window.telegram;
    const hasTelegramObject = typeof telegramObject !== 'undefined' && telegramObject !== null;
    const hasTelegramWebApp = !!(telegramObject && telegramObject.WebApp);
    const hasTelegramProxy =
        typeof window.TelegramWebviewProxy !== 'undefined' ||
        typeof window.TelegramGameProxy !== 'undefined';
    const isTelegramUserAgent = /Telegram|TgWebView|Telegram-Android|Telegram-iOS/i.test(ua);
    const isTelegramBrowser = hasTelegramWebApp || hasTelegramProxy || isTelegramUserAgent;
    const isMobilePhoneUserAgent = /Android|iPhone|iPod|Windows Phone|webOS|BlackBerry|IEMobile|Opera Mini/i.test(ua);

    function isMobilePhoneViewport() {
        return window.matchMedia('(max-width: 768px)').matches && window.matchMedia('(pointer: coarse)').matches;
    }

    function syncTelegramClasses() {
        document.documentElement.classList.toggle('is-telegram-browser', isTelegramBrowser);
        document.documentElement.classList.toggle(
            'is-telegram-mobile',
            hasTelegramObject && (isMobilePhoneUserAgent || isMobilePhoneViewport())
        );
    }

    syncTelegramClasses();
    window.addEventListener('resize', syncTelegramClasses);

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
