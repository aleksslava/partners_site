from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.utils.translation import gettext_lazy as _
from django.forms.models import BaseInlineFormSet
from django.core.exceptions import ValidationError

from .models import User, Address, Customer

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
        "phone",
        "city",
        "street",
        "house",
        "apartment",
        "postcode",
    )
    ordering = ("-is_default", "id")

class UserInline(admin.TabularInline):
    model = User
    extra = 0
    fields = ("username", "first_name", "last_name", "email", "phone", "role", "is_active", "is_staff")
    readonly_fields = ()
    show_change_link = True

@admin.register(Customer)
class CustomerAdmin(admin.ModelAdmin):
    list_display = ("id", "amo_id_customer", "partner_status", "partner_discount", "bonuses", "total_buyout")
    list_filter = ("partner_status",)
    search_fields = ("amo_id_customer",)
    readonly_fields = ("partner_discount", "time_created", "time_updated")
    inlines = [UserInline]

@admin.register(User)
class UserAdmin(BaseUserAdmin):
    model = User

    list_display = (
        "username", "first_name", "last_name",
        "customer", "role",
        "email", "phone", "telegram_id",
        "is_staff", "is_active", "is_superuser",
    )
    list_filter = ("role", "is_staff", "is_active", "is_superuser", "groups")
    search_fields = ("username", "first_name", "last_name", "email", "phone", "telegram_id", "amo_id_contact", "customer__amo_id_customer")
    ordering = ("-date_joined",)

    readonly_fields = ("last_login", "date_joined", "time_created", "time_updated")

    fieldsets = (
        (None, {"fields": ("username", "password")}),
        (_("Персональные данные"), {"fields": ("first_name", "last_name")}),
        (_("Связь с покупателем"), {"fields": ("customer", "role")}),
        (_("Контакты"), {"fields": ("email", "phone")}),
        (_("Интеграции"), {"fields": ("amo_id_contact", "telegram_id")}),
        (_("Права доступа"), {"fields": ("is_active", "is_staff", "is_superuser", "groups", "user_permissions")}),
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

    inlines = [AddressInline]
