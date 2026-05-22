import logging
from urllib.parse import urlencode

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import login as auth_login
from django.contrib.auth import update_session_auth_hash
from django.contrib.auth.decorators import login_required
from django.contrib.auth.views import LoginView
from django.db import transaction
from django.db.models import Sum
from django.http import HttpResponse
from django.shortcuts import redirect, render
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_http_methods

from integrations.amocrm.exceptions import AmoCRMError, ContactCustomerBindingError
from orders.models import Cart, Order
from users.forms import CabinetCredentialsForm, CabinetRequisitesForm
from users.models import User
from users.services.amocrm_login import (
    extract_error_message,
    get_external_identity,
    get_local_user_by_external_identity,
    resolve_user_via_amocrm,
)
from users.services.amocrm_sync import sync_user_and_customer_from_amocrm

logger = logging.getLogger(__name__)


def embedded_webapp_entry(request, platform: str):
    if platform not in settings.EMBEDDED_WEBAPP_FRAME_ANCESTORS:
        return redirect(settings.LOGIN_URL)

    next_url = request.GET.get("next") or settings.LOGIN_REDIRECT_URL
    is_safe_next = url_has_allowed_host_and_scheme(
        next_url,
        allowed_hosts={request.get_host()},
        require_https=request.is_secure(),
    )
    if not is_safe_next:
        next_url = settings.LOGIN_REDIRECT_URL

    request.session[settings.EMBEDDED_WEBAPP_SESSION_KEY] = platform
    return redirect(f"{settings.LOGIN_URL}?{urlencode({'next': next_url})}")


def _compose_delivery_address_text(city: str, street: str, house: str) -> str:
    return f"город {city}, улица {street}, дом {house}"


def _parse_object_id(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _clear_active_carts_requisites(requisites):
    Cart.objects.filter(
        requisites=requisites,
        status=Cart.Status.ACTIVE,
    ).update(requisites=None)


def _clear_active_carts_address(address):
    Cart.objects.filter(
        address=address,
        status=Cart.Status.ACTIVE,
    ).update(address=None)


class UserLoginView(LoginView):
    template_name = "users/login.html"
    redirect_authenticated_user = True
    auth_exec_param = "auth_exec"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["embedded_webapp_platform"] = self.request.session.get(
            settings.EMBEDDED_WEBAPP_SESSION_KEY,
            "",
        )
        return context

    def get(self, request, *args, **kwargs):
        if request.user.is_authenticated:
            return redirect(self.get_success_url())

        identity = get_external_identity(request)
        if identity is None:
            return super().get(request, *args, **kwargs)

        if request.GET.get(self.auth_exec_param) != "1":
            auth_query_params = request.GET.copy()
            auth_query_params[self.auth_exec_param] = "1"
            return render(
                request,
                "users/login_loading.html",
                {"auth_redirect_url": f"{request.path}?{auth_query_params.urlencode()}"},
            )

        field_name, field_value = identity
        user = get_local_user_by_external_identity(field_name=field_name, field_value=field_value)

        if user is None:
            try:
                user = resolve_user_via_amocrm(field_name=field_name, field_value=field_value)
            except (AmoCRMError, ContactCustomerBindingError) as error:
                logger.exception(
                    "AMO auth flow failed for %s=%s",
                    field_name,
                    field_value,
                )
                return render(
                    request,
                    "shop/error.html",
                    {"error_message": extract_error_message(error, "Произошла ошибка")},
                )
            except Exception:
                logger.exception(
                    "Unexpected error during AMO auth flow for %s=%s",
                    field_name,
                    field_value,
                )
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
        cabinet_action = request.POST.get("cabinet_action")

        if cabinet_action == "update_requisites":
            requisites_id = _parse_object_id(request.POST.get("requisites_id"))
            requisites = user.requisites_set.filter(pk=requisites_id).first() if requisites_id is not None else None

            if requisites is None:
                messages.error(request, "Реквизиты не найдены.")
            else:
                form = CabinetRequisitesForm(request.POST, instance=requisites, user=user)
                if form.is_valid():
                    form.save()
                    messages.success(request, "Реквизиты обновлены.")
                else:
                    for _field_name, field_errors in form.errors.items():
                        for error in field_errors:
                            messages.error(request, error)

            return redirect("users:user_cabinet")

        if cabinet_action == "delete_requisites":
            requisites_id = _parse_object_id(request.POST.get("requisites_id"))
            requisites = user.requisites_set.filter(pk=requisites_id).first() if requisites_id is not None else None

            if requisites is None:
                messages.error(request, "Реквизиты не найдены.")
            else:
                with transaction.atomic():
                    _clear_active_carts_requisites(requisites)
                    if requisites.orders.exists():
                        requisites.user = None
                        requisites.is_default = False
                        requisites.save(update_fields=["user", "is_default", "time_updated"])
                    else:
                        requisites.delete()

                messages.success(request, "Реквизиты удалены из кабинета.")

            return redirect("users:user_cabinet")

        if cabinet_action == "delete_address":
            address_id = _parse_object_id(request.POST.get("address_id"))
            address = user.addresses.filter(pk=address_id).first() if address_id is not None else None

            if address is None:
                messages.error(request, "Адрес не найден.")
            else:
                with transaction.atomic():
                    _clear_active_carts_address(address)
                    if address.orders.exists():
                        address.user = None
                        address.is_default = False
                        address.save(update_fields=["user", "is_default", "time_updated"])
                    else:
                        address.delete()

                messages.success(request, "Адрес удалён из кабинета.")

            return redirect("users:user_cabinet")

        if cabinet_action == "update_address":
            address_id = _parse_object_id(request.POST.get("address_id"))
            address = user.addresses.filter(pk=address_id).first() if address_id is not None else None
            label = (request.POST.get("label") or "").strip()

            if address is None:
                messages.error(request, "Адрес не найден.")
            elif not label:
                messages.error(request, "Укажите название адреса.")
            else:
                city = (request.POST.get("city") or "").strip()
                street = (request.POST.get("street") or "").strip()
                house = (request.POST.get("house") or "").strip()

                address.label = label
                address.city = city
                address.street = street
                address.house = house
                address.recipient_name = (request.POST.get("recipient_name") or "").strip()
                address.recipient_phone = (request.POST.get("recipient_phone") or "").strip()
                address.delivery_address_text = _compose_delivery_address_text(city, street, house)
                address.save(update_fields=[
                    "label",
                    "city",
                    "street",
                    "house",
                    "recipient_name",
                    "recipient_phone",
                    "delivery_address_text",
                    "time_updated",
                ])
                messages.success(request, "Адрес обновлён.")

            return redirect("users:user_cabinet")

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
            logger.exception(
                "Failed to sync user and customer from amoCRM for user_id=%s",
                request.user.id,
            )
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
    saved_addresses = user.addresses.order_by("-time_updated", "-id")
    saved_requisites = user.requisites_set.order_by("-time_updated", "-id")

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
            "saved_addresses": saved_addresses,
            "saved_requisites": saved_requisites,
        },
    )
