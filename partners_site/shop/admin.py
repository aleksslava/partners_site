from django.contrib import admin
from .models import Product, Image, Video, Category, Instruction, Characteristics
from django.db import models
# Register your models here.

admin.site.register([Image, Video, Category, Instruction])

class ProductTypeFilter(admin.SimpleListFilter):
    title = 'Тип товара'                # заголовок фильтра в админке
    parameter_name = 'product_type'     # имя параметра в URL

    def lookups(self, request, model_admin):
        return (
            ('main', 'Основной товар'),
            ('mod', 'Модификация'),
        )

    def queryset(self, request, queryset):
        value = self.value()
        if value == 'main':
            # Только основные товары (без родителя)
            return queryset.filter(parent__isnull=True)
        if value == 'mod':
            # Только модификации (есть родитель)
            return queryset.filter(parent__isnull=False)
        return queryset

class ParentProductFilter(admin.SimpleListFilter):
    title = 'Основной товар'
    parameter_name = 'parent_product'

    def lookups(self, request, model_admin):
        # показываем только основные товары (parent is null)
        mains = Product.objects.filter(parent__isnull=True)
        return [(p.id, p.name) for p in mains]

    def queryset(self, request, queryset):
        value = self.value()
        if value:
            # показываем и сам основной товар, и его модификации
            return queryset.filter(
                models.Q(id=value) | models.Q(parent_id=value)
            )
        return queryset

class ImageInline(admin.TabularInline):
    model = Image
    extra = 1

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
    inlines = [CharacteristicsInline, ModificationInline, ImageInline, VideoInline, InstructionInline]
    list_display = ('name', 'parent', 'is_main_product')
    list_filter = (ProductTypeFilter, ParentProductFilter)

    def is_main_product(self, obj):
        return obj.parent is None

    is_main_product.boolean = True
    is_main_product.short_description = 'Основной?'

