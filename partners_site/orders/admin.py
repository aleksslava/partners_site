from django.contrib import admin

from .models import Cart, CartItem


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
