from django.contrib import admin
from .models import Product, Image, Video, Category, Instruction, Characteristics, ProductGroup


from django.db import models
# Register your models here.

admin.site.register([Image, Video, Category, Instruction])


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



