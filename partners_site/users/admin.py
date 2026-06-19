import logging
from typing import Any

from django import forms
from django.contrib import admin, messages
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.core.exceptions import PermissionDenied, ValidationError
from django.utils.translation import gettext_lazy as _
from django.utils.html import format_html, format_html_join
from django.forms.models import BaseInlineFormSet
from django.http import HttpResponseRedirect
from django.urls import path, reverse

from integrations.amocrm.exceptions import AmoCRMError
from .models import User, Address, Customer, UserPhone, Requisites
from orders.models import Cart
from users.services.amocrm_login import (
    extract_error_message,
    parse_external_id,
    resolve_user_via_amocrm_contact_id,
)

logger = logging.getLogger(__name__)


class AmoContactCreateWidget(forms.Widget):
    """Render the amoCRM contact ID input with an admin submit button."""

    def __init__(
        self,
        base_widget: forms.Widget,
        create_url: str,
        attrs: dict[str, object] | None = None,
    ) -> None:
        super().__init__(attrs)
        self.base_widget = base_widget
        self.create_url = create_url

    @property
    def media(self) -> forms.Media:
        return self.base_widget.media + forms.Media(
            css={"all": ("admin/css/amo_contact_create.css",)},
            js=("admin/js/amo_contact_create.js",),
        )

    def render(
        self,
        name: str,
        value: Any,
        attrs: dict[str, object] | None = None,
        renderer: object | None = None,
    ) -> str:
        widget_html = self.base_widget.render(
            name,
            value,
            attrs=attrs,
            renderer=renderer,
        )
        return format_html(
            '<div class="amo-contact-create-widget">{}'
            '<button type="submit" class="button" formaction="{}" '
            'formmethod="post" formnovalidate disabled '
            'data-amo-contact-create-button>'
            "{}</button></div>",
            widget_html,
            self.create_url,
            "Создать по ID AmoCrm",
        )


class AddressInlineFormSet(BaseInlineFormSet):
    def clean(self):
        super().clean()

        default_count = 0

        for form in self.forms:
            # форма может быть пустой или удаляемой
            if not hasattr(form, "cleaned_data"):
                continue
            if form.cleaned_data.get("DELETE"):
                continue

            if form.cleaned_data.get("is_default"):
                default_count += 1

        if default_count > 1:
            raise ValidationError(
                "У пользователя может быть только один адрес «по умолчанию»."
            )


class AddressInline(admin.TabularInline):
    model = Address
    formset = AddressInlineFormSet
    extra = 0
    min_num = 0
    can_delete = True
    show_change_link = True

    fields = (
        "is_default",
        "label",
        "recipient_name",
        "recipient_phone",
        "delivery_address_text",
        "street",
        "house",
        "apartment",
        "postcode",
    )
    ordering = ("-is_default", "id")

class UserPhoneInline(admin.TabularInline):
    model = UserPhone
    extra = 0
    fields = ("phone",)


class RequisitesInline(admin.TabularInline):
    model = Requisites
    extra = 0
    fields = ("company_name", "inn", "kpp", "bik", "settlement_account", "is_default")
    show_change_link = True


class UserInline(admin.TabularInline):
    model = User
    extra = 0
    fields = ("username", "first_name", "last_name", "email", "phone", "role", "is_active", "is_staff")
    readonly_fields = ()
    show_change_link = True


class CartInline(admin.TabularInline):
    model = Cart
    extra = 0
    can_delete = False
    show_change_link = True
    verbose_name = "Корзина"
    verbose_name_plural = "Корзина"

    fields = (
        "id",
        "status",
        "delivery_type",
        "payment_type",
        "items_subtotal",
        "discount_total",
        "total",
        "time_updated",
    )
    readonly_fields = fields

    def has_add_permission(self, request, obj=None):
        return False



@admin.register(Customer)
class CustomerAdmin(admin.ModelAdmin):
    list_display = ("name", "amo_id_customer", "partner_status", "partner_discount", "bonuses", "total_buyout")
    list_filter = ("partner_status",)
    search_fields = ("name", "amo_id_customer")
    readonly_fields = ("partner_discount", "time_created", "time_updated", "cart_records")
    fieldsets = (
        (None, {"fields": ("name", "amo_id_customer", "partner_status", "partner_discount")}),
        (_("Финансы"), {"fields": ("bonuses", "total_buyout", "buyout_per_quater")}),
        (_("Корзина"), {"fields": ("cart_records",)}),
        (_("Даты"), {"fields": ("time_created", "time_updated")}),
    )
    inlines = [UserInline]

    def cart_records(self, obj):
        if not obj:
            return "-"

        carts = (
            Cart.objects
            .select_related("user")
            .filter(user__customer=obj)
            .order_by("-time_updated")
        )

        if not carts.exists():
            return "Нет связанных корзин"

        rows = [
            (
                reverse("admin:orders_cart_change", args=[cart.id]),
                cart.id,
                str(cart.user) if cart.user_id else "—",
                cart.get_status_display(),
                cart.total,
                cart.time_updated.strftime("%d.%m.%Y %H:%M"),
            )
            for cart in carts[:50]
        ]

        return format_html_join(
            format_html("<br>"),
            '<a href="{}">#{}</a> | {} | {} | {} ₽ | {}',
            rows,
        )

    cart_records.short_description = "Связанные корзины"

@admin.register(User)
class UserAdmin(BaseUserAdmin):
    model = User

    inlines = [AddressInline, UserPhoneInline, RequisitesInline, CartInline]

    list_display = (
        "login", "first_name", "last_name",
        "customer", "role_badge",
        "email", "phone",
        "address_count",
        "is_staff", "is_active",
    )
    list_display_links = ("login", "first_name", "last_name")
    list_select_related = ("customer",)
    date_hierarchy = "date_joined"
    autocomplete_fields = ("customer",)

    actions = ("activate_users", "deactivate_users", "make_manager", "make_client")

    list_filter = ("role", "is_staff", "is_active", "is_superuser", "groups")
    search_fields = ("username", "first_name", "last_name", "email", "phone", "telegram_id", "amo_id_contact", "customer__amo_id_customer")
    ordering = ("-date_joined",)

    readonly_fields = ("last_login", "date_joined", "time_created", "time_updated")

    _ROLE_COLORS = {
        User.Role.CUSTOMER: "#6c757d",
        User.Role.MANAGER: "#0d6efd",
        User.Role.ADMIN: "#dc3545",
    }
    _NON_SUPERUSER_HIDDEN_FIELDS = {
        "groups",
        "is_staff",
        "is_superuser",
        "user_permissions",
    }

    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            path(
                "create-from-amocrm/",
                self.admin_site.admin_view(self.create_from_amocrm),
                name="users_user_create_from_amocrm",
            ),
        ]
        return custom_urls + urls

    def get_form(self, request, obj=None, **kwargs):
        request._user_admin_add_form = obj is None
        return super().get_form(request, obj=obj, **kwargs)

    def get_fieldsets(self, request, obj=None):
        fieldsets = super().get_fieldsets(request, obj=obj)
        if request.user.is_superuser:
            return fieldsets

        filtered_fieldsets = []
        for name, options in fieldsets:
            fields = tuple(
                field
                for field in options["fields"]
                if field not in self._NON_SUPERUSER_HIDDEN_FIELDS
            )
            filtered_fieldsets.append((name, {**options, "fields": fields}))
        return tuple(filtered_fieldsets)

    def has_change_permission(self, request, obj=None):
        if obj is not None and obj.is_superuser and not request.user.is_superuser:
            return False
        return super().has_change_permission(request, obj=obj)

    def has_view_permission(self, request, obj=None):
        if obj is not None and obj.is_superuser and not request.user.is_superuser:
            return False
        return super().has_view_permission(request, obj=obj)

    def has_delete_permission(self, request, obj=None):
        if obj is not None and obj.is_superuser and not request.user.is_superuser:
            return False
        return super().has_delete_permission(request, obj=obj)

    def formfield_for_dbfield(self, db_field, request, **kwargs):
        formfield = super().formfield_for_dbfield(db_field, request, **kwargs)
        if db_field.name == "username" and formfield is not None:
            formfield.label = "Логин"
        if (
            db_field.name == "amo_id_contact"
            and formfield is not None
            and getattr(request, "_user_admin_add_form", False)
        ):
            formfield.widget = AmoContactCreateWidget(
                base_widget=formfield.widget,
                create_url=reverse("admin:users_user_create_from_amocrm"),
            )
        return formfield

    def create_from_amocrm(self, request):
        if not self.has_add_permission(request):
            raise PermissionDenied

        add_url = reverse("admin:users_user_add")
        if request.method != "POST":
            return HttpResponseRedirect(add_url)

        contact_id = parse_external_id(request.POST.get("amo_id_contact"))
        if contact_id is None:
            messages.error(request, "Введите корректный ID контакта AmoCRM.")
            return HttpResponseRedirect(add_url)

        try:
            user, created = resolve_user_via_amocrm_contact_id(contact_id=contact_id)
        except ValidationError as error:
            messages.error(request, error.messages[0] if error.messages else str(error))
            return HttpResponseRedirect(add_url)
        except AmoCRMError as error:
            messages.error(
                request,
                extract_error_message(
                    error,
                    "Не удалось создать пользователя из AmoCRM.",
                ),
            )
            return HttpResponseRedirect(add_url)
        except Exception:
            logger.exception(
                "Unexpected admin amoCRM user creation error for contact_id=%s",
                contact_id,
            )
            messages.error(request, "Не удалось создать пользователя из AmoCRM.")
            return HttpResponseRedirect(add_url)

        if created:
            messages.success(request, "Пользователь создан из AmoCRM.")
        else:
            messages.info(
                request,
                "Пользователь с таким ID контакта AmoCRM уже существует.",
            )

        return HttpResponseRedirect(reverse("admin:users_user_change", args=[user.pk]))

    @admin.display(description="Логин", ordering="username")
    def login(self, obj):
        return obj.username

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        if not request.user.is_superuser:
            qs = qs.filter(is_superuser=False)
        return qs.prefetch_related("addresses", "phones", "requisites_set")

    @admin.display(description=_("Роль"), ordering="role")
    def role_badge(self, obj):
        color = self._ROLE_COLORS.get(obj.role, "#6c757d")
        return format_html(
            '<span style="background:{};color:#fff;padding:2px 8px;'
            'border-radius:10px;font-size:11px;">{}</span>',
            color,
            obj.get_role_display(),
        )

    @admin.display(description=_("Адресов"))
    def address_count(self, obj):
        return len(obj.addresses.all())

    @admin.action(description=_("Активировать выбранных пользователей"))
    def activate_users(self, request, queryset):
        updated = queryset.update(is_active=True)
        self.message_user(request, _("Активировано пользователей: %d") % updated)

    @admin.action(description=_("Деактивировать выбранных пользователей"))
    def deactivate_users(self, request, queryset):
        updated = queryset.update(is_active=False)
        self.message_user(request, _("Деактивировано пользователей: %d") % updated)

    @admin.action(description=_("Сменить роль на «Менеджер»"))
    def make_manager(self, request, queryset):
        updated = queryset.update(role=User.Role.MANAGER)
        self.message_user(request, _("Роль изменена у: %d") % updated)

    @admin.action(description=_("Сменить роль на «Клиент»"))
    def make_client(self, request, queryset):
        updated = queryset.update(role=User.Role.CUSTOMER)
        self.message_user(request, _("Роль изменена у: %d") % updated)

    fieldsets = (
        (None, {"fields": ("username", "password")}),
        (_("Персональные данные"), {"fields": ("first_name", "last_name")}),
        (_("Связь с покупателем"), {"fields": ("customer", "role")}),
        (_("Контакты"), {"fields": ("email", "phone")}),
        (_("Интеграции"), {"fields": ("amo_id_contact", "telegram_id", "max_id")}),
        (_("Права доступа"), {
            "fields": (
                "is_active",
                "is_staff",
                "is_superuser",
                "groups",
                "user_permissions",
            ),
        }),
        (_("Даты"), {"fields": ("last_login", "date_joined", "time_created", "time_updated")}),
    )


    add_fieldsets = (
        (None, {
            "classes": ("wide",),
            "fields": (
                "username",
                "first_name", "last_name",
                "email", "phone",
                "customer", "role",
                "telegram_id", "amo_id_contact",
                "password1", "password2",
                "is_active", "is_staff",
            ),
        }),
    )


@admin.register(Address)
class AddressAdmin(admin.ModelAdmin):
    list_display = (
        "user", "label", "city", "street", "house", "apartment",
        "is_default", "time_updated",
    )
    list_filter = ("is_default", "country", "city")
    search_fields = (
        "user__username", "user__phone",
        "recipient_name", "recipient_phone",
        "city", "street", "postcode",
    )
    autocomplete_fields = ("user",)
    list_select_related = ("user",)
    date_hierarchy = "time_created"
    readonly_fields = ("time_created", "time_updated")


@admin.register(Requisites)
class RequisitesAdmin(admin.ModelAdmin):
    list_display = (
        "company_name", "user", "inn", "kpp", "settlement_account", "is_default",
    )
    list_filter = ("is_default",)
    search_fields = (
        "company_name", "inn", "kpp", "settlement_account",
        "user__username", "user__first_name", "user__last_name",
    )
    autocomplete_fields = ("user",)
    list_select_related = ("user",)
    readonly_fields = ("time_created", "time_updated")


@admin.register(UserPhone)
class UserPhoneAdmin(admin.ModelAdmin):
    list_display = ("user", "phone")
    search_fields = (
        "phone", "user__username", "user__first_name", "user__last_name",
    )
    autocomplete_fields = ("user",)
    list_select_related = ("user",)
