from datetime import timedelta

from django import forms
from django.contrib import admin
from django.db import transaction
from django.db.models import (
    ExpressionWrapper,
    F,
    IntegerField,
    OuterRef,
    Q,
    Subquery,
    Sum,
    Value,
)
from django.db.models.functions import Coalesce
from django.http import JsonResponse
from django.urls import path
from django.utils import timezone
from django.utils.html import format_html

from orders.models import CartItem, OrderItem

from .models import (
    Product,
    Image,
    Video,
    Category,
    CategoryStatusDiscountCap,
    Instruction,
    Characteristics,
    ProductGroup,
    RelatedProductGroup,
    RelatedProductStats,
)


# Register your models here.

admin.site.register([Image, Instruction])


@admin.register(Video)
class VideoAdmin(admin.ModelAdmin):
    search_fields = ('name', 'title')
    autocomplete_fields = ('products',)


class CategoryStatusDiscountCapInline(admin.TabularInline):
    model = CategoryStatusDiscountCap
    extra = 0
    fields = ("partner_status", "max_discount")


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ("name", "discount_policy", "discount")
    list_filter = ("discount_policy",)
    search_fields = ("name",)
    inlines = [CategoryStatusDiscountCapInline]


class ImageInlineForm(forms.ModelForm):
    class Meta:
        model = Image
        fields = "__all__"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['name'].required = False
        self.fields['title'].required = False

    def clean(self):
        cleaned_data = super().clean()
        photo = cleaned_data.get('photo') or getattr(self.instance, 'photo', None)
        if not photo:
            return cleaned_data

        caption = Image._build_caption_from_photo(getattr(photo, 'name', ''))
        if not (cleaned_data.get('name') or '').strip():
            cleaned_data['name'] = caption
        if not (cleaned_data.get('title') or '').strip():
            cleaned_data['title'] = caption
        return cleaned_data


class ImageInline(admin.TabularInline):
    model = Image
    extra = 0
    form = ImageInlineForm

class ProductVideoInline(admin.TabularInline):
    model = Video.products.through
    extra = 0
    autocomplete_fields = ('video',)

class ModificationInline(admin.TabularInline):
    model = Product
    extra = 0
    fk_name = 'parent'

class CharacteristicsInline(admin.TabularInline):
    model = Characteristics
    extra = 0

class InstructionInline(admin.TabularInline):
    model = Instruction
    extra = 0

@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    inlines = [CharacteristicsInline, ImageInline, ProductVideoInline, InstructionInline]
    list_display = ('name', 'group', 'is_primary', 'is_visible', 'price')
    list_filter = ('is_primary', 'is_visible', 'group__category')
    search_fields = ('name', 'amo_id')


class ProductInline(admin.TabularInline):
    model = Product
    fk_name = 'group'
    extra = 0
    fields = ('name', 'modification_name', 'price', 'is_primary', 'is_visible')
    show_change_link = True


class RelatedProductGroupInline(admin.TabularInline):
    model = RelatedProductGroup
    fk_name = 'source_group'
    extra = 0
    autocomplete_fields = ('related_group',)
    fields = ('related_group', 'sort_order', 'is_active')
    ordering = ('sort_order', 'id')


class RelatedStatsPeriodFilter(admin.SimpleListFilter):
    title = "Период"
    parameter_name = "related_stats_period"

    def lookups(self, request, model_admin):
        return (
            ("today", "Сегодня"),
            ("7d", "Последние 7 дней"),
            ("30d", "Последние 30 дней"),
        )

    def queryset(self, request, queryset):
        return queryset


def _get_related_stats_since(period: str | None):
    now = timezone.now()
    if period == "today":
        return now.replace(hour=0, minute=0, second=0, microsecond=0)
    if period == "7d":
        return now - timedelta(days=7)
    if period == "30d":
        return now - timedelta(days=30)
    return None


def _money_amount_expression():
    return ExpressionWrapper(
        F("current_unit_price_discounted") * F("related_added_qty"),
        output_field=IntegerField(),
    )


def _format_rubles(value: int | None) -> str:
    amount = int(value or 0)
    return f"{amount:,}".replace(",", " ") + " ₽"


@admin.register(RelatedProductStats)
class RelatedProductStatsAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "group",
        "category_name",
        "cart_related_qty",
        "cart_related_amount",
        "order_related_qty",
        "order_related_amount",
    )
    list_display_links = None
    list_filter = (RelatedStatsPeriodFilter, "group__category", "group")
    search_fields = ("name", "amo_id", "group__name")
    ordering = ("name",)
    actions = None

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    def get_queryset(self, request):
        qs = super().get_queryset(request).select_related("group", "group__category")
        since = _get_related_stats_since(request.GET.get("related_stats_period"))

        cart_items = CartItem.objects.filter(
            product_id=OuterRef("pk"),
            related_added_qty__gt=0,
        )
        order_items = OrderItem.objects.filter(
            product_id=OuterRef("pk"),
            related_added_qty__gt=0,
        )
        if since is not None:
            cart_items = cart_items.filter(cart__time_created__gte=since)
            order_items = order_items.filter(order__time_created__gte=since)

        cart_qty = (
            cart_items
            .values("product_id")
            .annotate(total=Sum("related_added_qty"))
            .values("total")
        )
        cart_amount = (
            cart_items
            .values("product_id")
            .annotate(total=Sum(_money_amount_expression()))
            .values("total")
        )
        order_qty = (
            order_items
            .values("product_id")
            .annotate(total=Sum("related_added_qty"))
            .values("total")
        )
        order_amount = (
            order_items
            .values("product_id")
            .annotate(total=Sum(_money_amount_expression()))
            .values("total")
        )

        return (
            qs.annotate(
                related_cart_qty=Coalesce(
                    Subquery(cart_qty, output_field=IntegerField()),
                    Value(0),
                ),
                related_cart_amount=Coalesce(
                    Subquery(cart_amount, output_field=IntegerField()),
                    Value(0),
                ),
                related_order_qty=Coalesce(
                    Subquery(order_qty, output_field=IntegerField()),
                    Value(0),
                ),
                related_order_amount=Coalesce(
                    Subquery(order_amount, output_field=IntegerField()),
                    Value(0),
                ),
            )
            .filter(Q(related_cart_qty__gt=0) | Q(related_order_qty__gt=0))
        )

    @admin.display(description="Категория", ordering="group__category__name")
    def category_name(self, obj):
        return obj.group.category if obj.group_id else ""

    @admin.display(description="Добавлено, шт.", ordering="related_cart_qty")
    def cart_related_qty(self, obj):
        return obj.related_cart_qty

    @admin.display(description="Добавлено, сумма", ordering="related_cart_amount")
    def cart_related_amount(self, obj):
        return _format_rubles(obj.related_cart_amount)

    @admin.display(description="Оформлено, шт.", ordering="related_order_qty")
    def order_related_qty(self, obj):
        return obj.related_order_qty

    @admin.display(description="Оформлено, сумма", ordering="related_order_amount")
    def order_related_amount(self, obj):
        return _format_rubles(obj.related_order_amount)


@admin.register(ProductGroup)
class ProductGroupAdmin(admin.ModelAdmin):
    list_display = ('drag_handle', 'name', 'category', 'sort_order', 'is_pinned')
    list_display_links = ('name',)
    list_filter = ('category', 'tags', 'is_pinned')
    list_editable = ('is_pinned', 'sort_order')
    ordering = ('sort_order', 'id')
    search_fields = ('name',)
    inlines = [ProductInline, RelatedProductGroupInline]

    class Media:
        css = {
            'all': ('admin/css/product_group_sortable.css',)
        }
        js = ('admin/js/product_group_sortable.js',)

    @admin.display(description='')
    def drag_handle(self, obj):
        return format_html('<span class="productgroup-drag-handle" aria-hidden="true">☰</span>')

    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            path(
                'reorder/',
                self.admin_site.admin_view(self.reorder_view),
                name='shop_productgroup_reorder',
            ),
        ]
        return custom_urls + urls

    @transaction.atomic
    def reorder_view(self, request):
        if request.method != 'POST':
            return JsonResponse({'success': False, 'error': 'method_not_allowed'}, status=405)
        if not self.has_change_permission(request):
            return JsonResponse({'success': False, 'error': 'permission_denied'}, status=403)

        import json
        try:
            payload = json.loads(request.body or '{}')
        except json.JSONDecodeError:
            return JsonResponse({'success': False, 'error': 'invalid_json'}, status=400)

        raw_ids = payload.get('ordered_ids') or []
        try:
            ordered_ids = [int(value) for value in raw_ids]
        except (TypeError, ValueError):
            return JsonResponse({'success': False, 'error': 'invalid_ids'}, status=400)

        if not ordered_ids:
            return JsonResponse({'success': False, 'error': 'empty_ids'}, status=400)

        groups = list(ProductGroup.objects.select_for_update().filter(id__in=ordered_ids))
        if len(groups) != len(set(ordered_ids)):
            return JsonResponse({'success': False, 'error': 'unknown_ids'}, status=400)

        groups_by_id = {group.id: group for group in groups}
        start_position = min(group.sort_order for group in groups)
        positions = {}

        for index, group_id in enumerate(ordered_ids):
            group = groups_by_id[group_id]
            group.sort_order = start_position + index
            positions[str(group_id)] = group.sort_order

        ProductGroup.objects.bulk_update(groups, ['sort_order'])
        return JsonResponse({'success': True, 'positions': positions})
