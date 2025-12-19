from django.db import models
from django.db.models import Q
from taggit.managers import TaggableManager





class Category(models.Model):
    name = models.CharField(max_length=255, verbose_name='Название')
    discount =models.IntegerField(verbose_name='Скидка на категорию')
    time_created = models.DateTimeField(auto_now_add=True, verbose_name='Дата создания')
    time_updated = models.DateTimeField(auto_now=True, verbose_name='Дата изменения')

    class Meta:
        verbose_name = 'Категория'
        verbose_name_plural = 'Категории'

    def __str__(self):
        return self.name


class ProductGroup(models.Model):
    name = models.CharField(
        max_length=255,
        verbose_name='Семейство товаров'
    )
    # сюда при желании можно вынести общие поля: категория, скидка и т.п.
    category = models.ForeignKey(Category, on_delete=models.PROTECT, verbose_name='Категория товара')
    sort_order = models.PositiveIntegerField(default=0, db_index=True, verbose_name='Позиция в каталоге')
    is_pinned = models.BooleanField(default=False, db_index=True, verbose_name='Закрепить наверху')
    tags = TaggableManager(blank=True, verbose_name="Теги")

    @property
    def primary_product(self):
        qs = self.modifications.filter(is_visible=True)
        return qs.filter(is_primary=True).first() or qs.first()

    class Meta:
        verbose_name = 'Семейство товаров'
        verbose_name_plural = 'Семейства товаров'

    def __str__(self):
        return self.name

# Create your models here.
class Product(models.Model):
    name = models.CharField(max_length=255, verbose_name='Наименование')
    amo_id = models.PositiveIntegerField(verbose_name='id товара в amocrm')
    price = models.PositiveIntegerField(verbose_name='Цена')
    title = models.TextField(verbose_name='Описание')
    short_description = models.CharField(max_length=200, blank=True, verbose_name='Краткое описание')

    group = models.ForeignKey(
        ProductGroup,
        on_delete=models.CASCADE,
        related_name='modifications',
        verbose_name='Группа модификаций',
        null=True,
        blank=True,
    )

    is_primary = models.BooleanField(
        default=False,
        verbose_name='Основная модификация в группе',
    )

    is_visible = models.BooleanField(default=True, verbose_name='Видимость')
    limit = models.IntegerField(verbose_name='Лимит покупки', null=True, blank=True)
    tags = TaggableManager(verbose_name='Теги')
    time_created = models.DateTimeField(auto_now_add=True, verbose_name='Дата создания')
    time_updated = models.DateTimeField(auto_now=True, verbose_name='Дата изменения')

    class Meta:
        verbose_name = 'Товар'
        verbose_name_plural = 'Товары'
        constraints = [
            # В группе может быть только ОДНА основная модификация
            models.UniqueConstraint(
                fields=['group'],
                condition=Q(is_primary=True),
                name='unique_primary_modification_per_group'
            )
        ]

    def __str__(self):
        return self.name

class Image(models.Model):
    name = models.CharField(max_length=255, verbose_name='Наименование')
    title = models.CharField(max_length=255, verbose_name='Описание')
    photo = models.ImageField(upload_to='products/', verbose_name='Фото')
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='images')
    time_created = models.DateTimeField(auto_now_add=True, verbose_name='Дата создания')
    time_updated = models.DateTimeField(auto_now=True, verbose_name='Дата изменения')

    class Meta:
        verbose_name = 'Фото'
        verbose_name_plural = 'Изображения'


    def __str__(self):
        return self.name

class Characteristics(models.Model):
    key = models.CharField(max_length=300, verbose_name='Характеристика')
    value = models.CharField(max_length=300, verbose_name='Значение')
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='characteristics')

    class Meta:
        verbose_name = 'Характеристика'
        verbose_name_plural = "Характеристики"

class Video(models.Model):
    name = models.CharField(max_length=255, verbose_name='Наименование')
    title = models.CharField(max_length=255, verbose_name='Описание')
    video = models.FileField(upload_to='products/', verbose_name='Видео')
    product = models.ForeignKey(Product, on_delete=models.CASCADE, verbose_name='Видео', related_name='videos')
    time_created = models.DateTimeField(auto_now_add=True, verbose_name='Дата создания')
    time_updated = models.DateTimeField(auto_now=True, verbose_name='Дата изменения')

    class Meta:
        verbose_name = 'Видео'
        verbose_name_plural = 'Видео'

    def __str__(self):
        return self.name


class Instruction(models.Model):
    name = models.CharField(max_length=255, verbose_name='Наименование')
    institution = models.FileField(upload_to='products', verbose_name='Файл инструкции')
    product = models.ForeignKey(Product, on_delete=models.CASCADE, verbose_name='Товар')
    time_created = models.DateTimeField(auto_now_add=True, verbose_name='Дата создания')
    time_updated = models.DateTimeField(auto_now=True, verbose_name='Дата изменения')

    class Meta:
        verbose_name = 'Инструкция'
        verbose_name_plural = 'Инструкции'

    def __str__(self):
        return self.name
