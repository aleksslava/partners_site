from django.contrib import messages
from django.contrib.auth import login as auth_login
from django.contrib.auth import update_session_auth_hash
from django.contrib.auth.decorators import login_required
from django.contrib.auth.views import LoginView
from django.db.models import Sum
from django.http import HttpResponse
from django.shortcuts import redirect, render
from django.views.decorators.http import require_http_methods

from integrations.amocrm.exceptions import AmoCRMError, ContactCustomerBindingError
from orders.models import Cart, Order
from users.forms import CabinetCredentialsForm
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


@require_http_methods(["GET", "POST"])
@login_required
def user_cabinet_view(request):
    user = (
        User.objects
        .select_related("customer")
        .get(pk=request.user.pk)
    )

    credentials_form = CabinetCredentialsForm(user=user, data=request.POST or None)

    if request.method == "POST":
        if credentials_form.is_valid():
            username_changed, password_changed = credentials_form.save()

            if password_changed:
                update_session_auth_hash(request, user)

            if username_changed and password_changed:
                messages.success(request, "Логин и пароль обновлены.")
            elif username_changed:
                messages.success(request, "Логин обновлён.")
            else:
                messages.success(request, "Пароль обновлён.")

            return redirect("users:user_cabinet")
    else:
        # Синхронизация данных из AMOCRM только на GET.
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
        credentials_form = CabinetCredentialsForm(user=user)

    orders = (
        Order.objects
        .filter(user=user)
        .select_related("address", "requisites")
        .prefetch_related("items", "items__product")
        .order_by("-time_created")
    )
    latest_order = orders.first()

    active_cart = (
        Cart.objects
        .filter(user=user, status=Cart.Status.ACTIVE)
        .select_related("address", "requisites")
        .prefetch_related("items")
        .order_by("-time_updated")
        .first()
    )
    active_cart_items_total = 0
    if active_cart is not None:
        active_cart_items_total = active_cart.items.aggregate(total_qty=Sum("qty")).get("total_qty") or 0

    default_address = (
        user.addresses
        .filter(is_default=True)
        .order_by("-time_updated")
        .first()
        or user.addresses.order_by("-time_updated").first()
    )
    default_requisites = (
        user.requisites_set
        .filter(is_default=True)
        .order_by("-time_updated")
        .first()
        or user.requisites_set.order_by("-time_updated").first()
    )

    return render(
        request,
        "users/cabinet.html",
        {
            "user": user,
            "orders": orders,
            "credentials_form": credentials_form,
            "latest_order": latest_order,
            "active_cart": active_cart,
            "active_cart_items_total": active_cart_items_total,
            "default_address": default_address,
            "default_requisites": default_requisites,
        },
    )
