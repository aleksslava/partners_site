from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.utils.translation import gettext_lazy as _
from django.utils.html import format_html, format_html_join
from django.forms.models import BaseInlineFormSet
from django.core.exceptions import ValidationError
from django.urls import reverse

from .models import User, Address, Customer, UserPhone, Requisites
from orders.models import Cart


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
        "username", "first_name", "last_name",
        "customer", "role_badge",
        "email", "phone",
        "address_count",
        "is_staff", "is_active",
    )
    list_display_links = ("username", "first_name", "last_name")
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

    def get_queryset(self, request):
        qs = super().get_queryset(request)
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
        (_("Права доступа"), {"fields": ("is_active", "is_staff", "is_superuser")}),
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
