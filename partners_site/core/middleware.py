from django.conf import settings
from django.shortcuts import redirect
from django.urls import resolve


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
        if path == settings.LOGIN_URL or path == "/logout/":
            return self.get_response(request)

        # Если пользователь уже авторизован — пускаем
        if request.user.is_authenticated:
            return self.get_response(request)

        # Иначе редирект на логин (с next=)
        return redirect(f"{settings.LOGIN_URL}?next={path}")
