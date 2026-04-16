from django.db import models
from django.db.models import Q
from django.core.files.base import ContentFile
from django.core.validators import MaxValueValidator, MinValueValidator
from taggit.managers import TaggableManager
from pathlib import Path
from io import BytesIO
from PIL import Image as PilImage, ImageOps
from users.models import Customer





class Category(models.Model):
    class DiscountPolicy(models.TextChoices):
        STANDARD = "standard", "Обычная"
        STATUS_CAPPED = "status_capped", "Лимит по статусу партнера"

    name = models.CharField(max_length=255, verbose_name='Название')
    discount =models.IntegerField(verbose_name='Скидка на категорию')
    discount_policy = models.CharField(
        max_length=20,
        choices=DiscountPolicy.choices,
        default=DiscountPolicy.STANDARD,
        verbose_name="Тип расчета скидки",
    )
    time_created = models.DateTimeField(auto_now_add=True, verbose_name='Дата создания')
    time_updated = models.DateTimeField(auto_now=True, verbose_name='Дата изменения')

    class Meta:
        verbose_name = 'Категория'
        verbose_name_plural = 'Категории'

    def __str__(self):
        return self.name


class CategoryStatusDiscountCap(models.Model):
    category = models.ForeignKey(
        Category,
        on_delete=models.CASCADE,
        related_name="status_caps",
        verbose_name="Категория",
    )
    partner_status = models.CharField(
        max_length=255,
        choices=Customer.PartnerStatus.choices,
        verbose_name="Статус партнера",
    )
    max_discount = models.PositiveSmallIntegerField(
        validators=[MinValueValidator(0), MaxValueValidator(100)],
        verbose_name="Максимальная скидка (%)",
    )

    class Meta:
        verbose_name = "Лимит скидки по статусу"
        verbose_name_plural = "Лимиты скидки по статусам"
        constraints = [
            models.UniqueConstraint(
                fields=["category", "partner_status"],
                name="unique_category_partner_status_discount_cap",
            )
        ]

    def __str__(self):
        return f"{self.category} / {self.get_partner_status_display()}: {self.max_discount}%"


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
    MAX_IMAGE_SIDE = 1600
    JPEG_QUALITY = 82
    WEBP_QUALITY = 80

    name = models.CharField(max_length=255, verbose_name='\u041d\u0430\u0438\u043c\u0435\u043d\u043e\u0432\u0430\u043d\u0438\u0435')
    title = models.CharField(max_length=255, verbose_name='\u041e\u043f\u0438\u0441\u0430\u043d\u0438\u0435')
    photo = models.ImageField(upload_to='products/', verbose_name='\u0424\u043e\u0442\u043e')
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='images')
    time_created = models.DateTimeField(auto_now_add=True, verbose_name='\u0414\u0430\u0442\u0430 \u0441\u043e\u0437\u0434\u0430\u043d\u0438\u044f')
    time_updated = models.DateTimeField(auto_now=True, verbose_name='\u0414\u0430\u0442\u0430 \u0438\u0437\u043c\u0435\u043d\u0435\u043d\u0438\u044f')

    class Meta:
        verbose_name = '\u0424\u043e\u0442\u043e'
        verbose_name_plural = '\u0418\u0437\u043e\u0431\u0440\u0430\u0436\u0435\u043d\u0438\u044f'

    @staticmethod
    def _build_caption_from_photo(photo_name: str) -> str:
        stem = Path(photo_name or '').stem
        caption = ' '.join(stem.replace('_', ' ').replace('-', ' ').split())
        return (caption or 'image')[:255]

    def _optimize_photo_if_needed(self):
        if not self.photo or getattr(self.photo, '_committed', True):
            return

        file_name = Path(self.photo.name)
        try:
            self.photo.open('rb')
            with PilImage.open(self.photo) as raw_image:
                image = ImageOps.exif_transpose(raw_image)
                if image.mode == 'P':
                    image = image.convert('RGBA')

                if max(image.size) > self.MAX_IMAGE_SIDE:
                    image.thumbnail(
                        (self.MAX_IMAGE_SIDE, self.MAX_IMAGE_SIDE),
                        PilImage.Resampling.LANCZOS,
                    )

                original_format = (raw_image.format or file_name.suffix.lstrip('.')).upper()
                output = BytesIO()

                if original_format in {'JPG', 'JPEG'}:
                    if image.mode not in {'RGB', 'L'}:
                        image = image.convert('RGB')
                    image.save(
                        output,
                        format='JPEG',
                        optimize=True,
                        progressive=True,
                        quality=self.JPEG_QUALITY,
                    )
                    new_suffix = '.jpg'
                elif original_format == 'PNG':
                    image.save(output, format='PNG', optimize=True, compress_level=9)
                    new_suffix = '.png'
                else:
                    if image.mode not in {'RGB', 'RGBA'}:
                        image = image.convert('RGB')
                    image.save(output, format='WEBP', quality=self.WEBP_QUALITY, method=6)
                    new_suffix = '.webp'

                output.seek(0)
                optimized_name = f"{file_name.stem}{new_suffix}"
                self.photo.save(optimized_name, ContentFile(output.read()), save=False)
        except Exception:
            # Fallback: keep original file if optimization failed.
            return
        finally:
            try:
                self.photo.close()
            except Exception:
                pass

    def save(self, *args, **kwargs):
        if self.photo:
            caption = self._build_caption_from_photo(getattr(self.photo, 'name', ''))
            if not (self.name or '').strip():
                self.name = caption
            if not (self.title or '').strip():
                self.title = caption

        self._optimize_photo_if_needed()
        super().save(*args, **kwargs)

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
    product = models.ForeignKey(Product, on_delete=models.CASCADE, verbose_name='Товар', related_name='instructions')
    time_created = models.DateTimeField(auto_now_add=True, verbose_name='Дата создания')
    time_updated = models.DateTimeField(auto_now=True, verbose_name='Дата изменения')

    class Meta:
        verbose_name = 'Инструкция'
        verbose_name_plural = 'Инструкции'

    def __str__(self):
        return self.name

