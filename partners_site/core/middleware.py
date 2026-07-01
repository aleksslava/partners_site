from urllib.parse import urlsplit

from django.conf import settings
from django.http import HttpRequest
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

EMBEDDED_WEBAPP_PUBLIC_PATHS = frozenset(
    (
        settings.LOGIN_REDIRECT_URL,
        settings.LOGIN_URL,
        "/telegram/",
        "/max/",
    )
)


def _get_origin(value: str) -> str | None:
    parsed = urlsplit(value)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return None
    return f"{parsed.scheme}://{parsed.netloc}".lower()


def _infer_embedded_platform(request: HttpRequest) -> str | None:
    origins = (
        _get_origin(request.headers.get("Origin", "")),
        _get_origin(request.headers.get("Referer", "")),
    )
    for platform, frame_ancestor in settings.EMBEDDED_WEBAPP_FRAME_ANCESTORS.items():
        if frame_ancestor.lower() in origins:
            return platform
    return None


def _build_frame_ancestors_csp(frame_ancestors: tuple[str, ...]) -> str:
    allowed_ancestors = " ".join(("'self'", *frame_ancestors))
    return (
        f"frame-ancestors {allowed_ancestors}; "
        "upgrade-insecure-requests; block-all-mixed-content"
    )


class EmbeddedWebAppFrameOptionsMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        platform = request.session.get(settings.EMBEDDED_WEBAPP_SESSION_KEY)
        if platform not in settings.EMBEDDED_WEBAPP_FRAME_ANCESTORS:
            platform = _infer_embedded_platform(request)
            if platform is not None:
                request.session[settings.EMBEDDED_WEBAPP_SESSION_KEY] = platform

        response = self.get_response(request)
        if request.path.startswith("/admin/"):
            return response

        frame_ancestor = settings.EMBEDDED_WEBAPP_FRAME_ANCESTORS.get(platform)
        if frame_ancestor is not None:
            frame_ancestors = (frame_ancestor,)
        elif request.path in EMBEDDED_WEBAPP_PUBLIC_PATHS:
            frame_ancestors = tuple(settings.EMBEDDED_WEBAPP_FRAME_ANCESTORS.values())
        else:
            return response

        response.xframe_options_exempt = True
        response.headers["Content-Security-Policy"] = _build_frame_ancestors_csp(
            frame_ancestors,
        )
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
