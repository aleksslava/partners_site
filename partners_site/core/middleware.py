from django.conf import settings
from django.shortcuts import redirect


PUBLIC_PATHS = frozenset(
    (
        settings.LOGIN_URL,
        "/logout/",
        "/telegram/",
        "/max/",
        "/customer/changed",
        "/landing",
        "/landing/",
    )
)


class EmbeddedWebAppFrameOptionsMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        if request.path.startswith("/admin/"):
            return response

        platform = request.session.get(settings.EMBEDDED_WEBAPP_SESSION_KEY)
        frame_ancestor = settings.EMBEDDED_WEBAPP_FRAME_ANCESTORS.get(platform)
        if frame_ancestor is None:
            return response

        response.xframe_options_exempt = True
        response.headers[
            "Content-Security-Policy"
        ] = f"frame-ancestors 'self' {frame_ancestor}; upgrade-insecure-requests; block-all-mixed-content"
        return response


class LoginRequiredMiddleware:
    """
    Закрывает весь сайт для неавторизованных пользователей.
    Исключения: login/logout/admin/static/media.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        path = request.path

        # Разрешаем статику/медиа
        if path.startswith("/static/") or path.startswith("/media/"):
            return self.get_response(request)

        # Разрешаем админку
        if path.startswith("/admin/"):
            return self.get_response(request)

        # Разрешаем страницы входа/выхода
        if path in PUBLIC_PATHS:
            return self.get_response(request)

        # Если пользователь уже авторизован — пускаем
        if request.user.is_authenticated:
            return self.get_response(request)

        # Иначе редирект на логин (с next=)
        return redirect(f"{settings.LOGIN_URL}?next={path}")
