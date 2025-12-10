from django.db import models
from taggit.managers import TaggableManager





class Category(models.Model):
    name = models.CharField(max_length=255)
    discont =models.IntegerField(verbose_name='Скидка на категорию')
    time_created = models.DateTimeField(auto_now_add=True, verbose_name='Дата создания')
    time_updated = models.DateTimeField(auto_now=True, verbose_name='Дата изменения')

    class Meta:
        verbose_name = 'Категория'
        verbose_name_plural = 'Категории'

    def __str__(self):
        return self.name

# Create your models here.
class Product(models.Model):
    name = models.CharField(max_length=255, verbose_name='Наименование')
    amo_id = models.PositiveIntegerField(verbose_name='id товара в amocrm')
    price = models.PositiveIntegerField(verbose_name='Цена')
    title = models.TextField(max_length=400, verbose_name='Описание')
    parent = models.ForeignKey('self', on_delete=models.SET_NULL, verbose_name='Основной товар',
                               related_name='modifications', null=True, blank=True)
    is_visible = models.BooleanField(default=True, verbose_name='Видимость')
    limit = models.IntegerField(verbose_name='Лимит покупки', null=True, blank=True)
    category = models.ForeignKey(Category, on_delete=models.PROTECT, verbose_name='Категория товара')
    tags = TaggableManager(verbose_name='Теги')
    time_created = models.DateTimeField(auto_now_add=True, verbose_name='Дата создания')
    time_updated = models.DateTimeField(auto_now=True, verbose_name='Дата изменения')

    class Meta:
        verbose_name = 'Товар'
        verbose_name_plural = 'Товары'

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
