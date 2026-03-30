from django.contrib.auth import login as auth_login
from django.contrib.auth.decorators import login_required
from django.contrib.auth.views import LoginView
from django.http import HttpResponse
from django.shortcuts import redirect, render
from django.views.decorators.http import require_GET

from integrations.amocrm.exceptions import AmoCRMError, ContactCustomerBindingError
from orders.models import Order
from users.models import User
from users.services.amocrm_login import (
    extract_error_message,
    get_external_identity,
    get_local_user_by_external_identity,
    resolve_user_via_amocrm,
)
from users.services.amocrm_sync import sync_user_and_customer_from_amocrm


class UserLoginView(LoginView):
    template_name = "users/login.html"
    redirect_authenticated_user = True

    def get(self, request, *args, **kwargs):
        if request.user.is_authenticated:
            return redirect(self.get_success_url())

        identity = get_external_identity(request)
        if identity is None:
            return super().get(request, *args, **kwargs)

        field_name, field_value = identity
        user = get_local_user_by_external_identity(field_name=field_name, field_value=field_value)

        if user is None:
            try:
                user = resolve_user_via_amocrm(field_name=field_name, field_value=field_value)
            except (AmoCRMError, ContactCustomerBindingError) as error:
                return render(
                    request,
                    "shop/error.html",
                    {"error_message": extract_error_message(error, "Произошла ошибка")},
                )
            except Exception:
                return render(
                    request,
                    "shop/error.html",
                    {"error_message": "Произошла ошибка связи с сервером, обратитесь к менеджеру"},
                )

        if user is None:
            return render(request, "shop/error.html", {"error_message": "ID пользователя не найден"})

        auth_login(request, user, backend="django.contrib.auth.backends.ModelBackend")
        return redirect(self.get_success_url())


@require_GET
@login_required
def user_cabinet_view(request):
    user = (
        User.objects
        .select_related("customer")
        .get(pk=request.user.pk)
    )

    # Синхронизация покупателя и контакта с данными из AMOCRM
    try:
        sync_result = sync_user_and_customer_from_amocrm(user=user, request=request)
        if isinstance(sync_result, HttpResponse):
            return sync_result
    except Exception:
        return render(
            request,
            "shop/error.html",
            {"error_message": "Не удалось синхронизировать данные, обратитесь к менеджеру"},
        )

    user = (
        User.objects
        .select_related("customer")
        .get(pk=request.user.pk)
    )

    orders = (
        Order.objects
        .filter(user=user)
        .select_related("address", "requisites")
        .prefetch_related("items", "items__product")
        .order_by("-time_created")
    )

    return render(
        request,
        "users/cabinet.html",
        {
            "user": user,
            "orders": orders,
        },
    )
