from django.contrib import admin
from django import forms
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
    extra = 1
    form = ImageInlineForm

class VideoInline(admin.TabularInline):
    model = Video
    extra = 1

class ModificationInline(admin.TabularInline):
    model = Product
    extra = 1
    fk_name = 'parent'

class CharacteristicsInline(admin.TabularInline):
    model = Characteristics
    extra = 3

class InstructionInline(admin.TabularInline):
    model = Instruction
    extra = 1

@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    inlines = [CharacteristicsInline, ImageInline, VideoInline, InstructionInline]
    list_display = ('name', 'group', 'is_primary', 'is_visible', 'price')
    list_filter = ('is_primary', 'is_visible', 'group__category')
    search_fields = ('name', 'amo_id')


class ProductInline(admin.TabularInline):
    model = Product
    fk_name = 'group'
    extra = 1
    fields = ('name', 'price', 'is_primary', 'is_visible')
    show_change_link = True

@admin.register(ProductGroup)
class ProductGroupAdmin(admin.ModelAdmin):
    list_display = ('name', 'category', 'sort_order', 'is_pinned')
    list_filter = ('category', 'tags', 'is_pinned')
    list_editable = ('is_pinned', 'sort_order')
    ordering = ('sort_order', '-is_pinned', 'id')
    inlines = [ProductInline]



