from django.contrib import admin

from .models import Cart, CartItem, Order, OrderItem


class CartItemInline(admin.TabularInline):
    model = CartItem
    extra = 0
    show_change_link = True
    fields = (
        "product",
        "qty",
        "discount_percent",
        "current_unit_price",
        "current_unit_price_discounted",
        "bonuses_append",
        "bonuses_spent",
        "line_total",
    )
    readonly_fields = (
        "product",
        "discount_percent",
        "current_unit_price",
        "current_unit_price_discounted",
        "bonuses_append",
        "bonuses_spent",
        "line_total",
        "time_created",
        "time_updated",
    )


@admin.register(Cart)
class CartAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "user",
        "status",
        "delivery_type",
        "payment_type",
        "items_subtotal",
        "discount_total",
        "total",
        "time_updated",
    )
    list_filter = (
        "status",
        "delivery_type",
        "payment_type",
        "discount_type",
        "time_created",
        "time_updated",
    )
    search_fields = (
        "id",
        "user__username",
        "user__email",
        "user__phone",
    )
    readonly_fields = ("time_created", "time_updated")
    inlines = [CartItemInline]


class OrderItemInline(admin.TabularInline):
    model = OrderItem
    extra = 0
    show_change_link = True
    fields = (
        "product",
        "qty",
        "discount_percent",
        "current_unit_price",
        "current_unit_price_discounted",
        "bonuses_append",
        "bonuses_spent",
        "line_total",
    )
    readonly_fields = (
        "product",
        "discount_percent",
        "current_unit_price",
        "current_unit_price_discounted",
        "bonuses_append",
        "bonuses_spent",
        "line_total",
        "time_created",
        "time_updated",
    )


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "user",
        "status",
        "delivery_type",
        "payment_type",
        "items_subtotal",
        "discount_total",
        "delivery_price",
        "total",
        "amo_crm_id",
        "time_created",
    )
    list_display_links = ("id", "user")
    list_filter = (
        "status",
        "delivery_type",
        "payment_type",
        "discount_type",
        "need_help",
        "time_created",
    )
    search_fields = (
        "id",
        "amo_crm_id",
        "user__username",
        "user__email",
        "user__phone",
        "delivery_service",
        "delivery_tariff",
    )
    autocomplete_fields = ("user", "address", "requisites")
    list_select_related = ("user", "address", "requisites")
    date_hierarchy = "time_created"
    ordering = ("-time_created",)
    readonly_fields = ("time_created", "time_updated")
    inlines = [OrderItemInline]

    fieldsets = (
        (None, {"fields": ("user", "status", "amo_crm_id", "comment", "need_help")}),
        ("Доставка", {
            "fields": (
                "delivery_type", "address",
                "delivery_service", "delivery_tariff", "delivery_price",
            ),
        }),
        ("Оплата и реквизиты", {"fields": ("payment_type", "requisites")}),
        ("Скидки и бонусы", {
            "fields": (
                "discount_type", "order_discount_percent",
                "bonuses_spent_total", "bonuses_append_total",
            ),
        }),
        ("Итоги", {"fields": ("items_subtotal", "discount_total", "total")}),
        ("Даты", {"fields": ("time_created", "time_updated")}),
    )
