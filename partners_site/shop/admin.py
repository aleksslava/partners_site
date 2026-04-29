from django.contrib import admin
from django import forms
from django.db import transaction
from django.http import JsonResponse
from django.urls import path
from django.utils.html import format_html
from .models import (
    Product,
    Image,
    Video,
    Category,
    CategoryStatusDiscountCap,
    Instruction,
    Characteristics,
    ProductGroup,
)


# Register your models here.

admin.site.register([Image, Video, Instruction])


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

class VideoInline(admin.TabularInline):
    model = Video
    extra = 0

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
    inlines = [CharacteristicsInline, ImageInline, VideoInline, InstructionInline]
    list_display = ('name', 'group', 'is_primary', 'is_visible', 'price')
    list_filter = ('is_primary', 'is_visible', 'group__category')
    search_fields = ('name', 'amo_id')


class ProductInline(admin.TabularInline):
    model = Product
    fk_name = 'group'
    extra = 0
    fields = ('name', 'modification_name', 'price', 'is_primary', 'is_visible')
    show_change_link = True

@admin.register(ProductGroup)
class ProductGroupAdmin(admin.ModelAdmin):
    list_display = ('drag_handle', 'name', 'category', 'sort_order', 'is_pinned')
    list_display_links = ('name',)
    list_filter = ('category', 'tags', 'is_pinned')
    list_editable = ('is_pinned', 'sort_order')
    ordering = ('sort_order', 'id')
    inlines = [ProductInline]

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


