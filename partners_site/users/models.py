from django.contrib.auth.models import AbstractUser
from django.db import models
from django.conf import settings
from django.db.models import CharField


class Customer(models.Model):

    class PartnerStatus(models.TextChoices):
        Start = 'start', 'Старт'
        Base = 'base', 'База'
        Bronze = 'bronze', 'Бронза'
        Silver = 'silver', 'Серебро'
        Gold = 'gold', 'Золото'
        Platina = 'platina', 'Платина'
        Business = 'business', 'Бизнес'
        Exclusive = 'exclusive', 'Эксклюзив'

    name = models.CharField(verbose_name='Наименование партнёра')

    amo_id_customer = models.IntegerField(blank=True, unique=True, null=True, verbose_name='ID покупателя в AMO')
    partner_status = models.CharField(max_length=255, default=PartnerStatus.Start,
                                      choices=PartnerStatus.choices, verbose_name='Статус партнёра')
    partner_discount = models.DecimalField(max_digits=2, default=0, decimal_places=0, verbose_name='Скидка покупателя')
    bonuses = models.IntegerField(verbose_name='Бонусы на балансе', default=0)
    total_buyout = models.IntegerField(verbose_name='Сумма чистого выкупа', default=0)
    buyout_per_quater = models.IntegerField(verbose_name='Сумма чистого выкупа за квартал', default=0)
    time_created = models.DateTimeField(auto_now_add=True, verbose_name='Дата создания')
    time_updated = models.DateTimeField(auto_now=True, verbose_name='Дата изменения')

    def save(self, *args, **kwargs):
        if self.partner_status == self.PartnerStatus.Start:
            self.partner_discount = 15
        elif self.partner_status == self.PartnerStatus.Base:
            self.partner_discount = 20
        elif self.partner_status == self.PartnerStatus.Bronze:
            self.partner_discount = 25
        elif self.partner_status == self.PartnerStatus.Silver:
            self.partner_discount = 30
        elif self.partner_status == self.PartnerStatus.Gold:
            self.partner_discount = 35
        elif self.partner_status == self.PartnerStatus.Platina:
            self.partner_discount = 40
        elif self.partner_status == self.PartnerStatus.Business:
            self.partner_discount = 40
        elif self.partner_status == self.PartnerStatus.Exclusive:
            self.partner_discount = 0
        super().save(*args, **kwargs)

    class Meta:
        verbose_name = 'Покупатель'
        verbose_name_plural = 'Покупатели'

    def __str__(self):
        return f'Покупатель id{self.amo_id_customer} ({self.name})'

# Модель для телефона



class User(AbstractUser):
    class Role(models.TextChoices):
        CUSTOMER = 'client', 'Клиент'
        MANAGER = 'manager', 'Менеджер'
        ADMIN = 'admin', 'Администратор'

    customer = models.ForeignKey(Customer, on_delete=models.CASCADE, verbose_name='Покупатель', related_name='users',
                                 null=True, blank=True)
    role = models.CharField(max_length=20, choices=Role.choices, default=Role.CUSTOMER, verbose_name='Тип пользователя')
    phone = models.CharField(max_length=32, blank=True, unique=True, null=True, verbose_name='Номер телефона')
    amo_id_contact = models.IntegerField(blank=True, null=True, verbose_name='ID контакта в AMO')
    telegram_id = models.IntegerField(blank=True, null=True, verbose_name='Телеграм ID')
    max_id = models.IntegerField(blank=True, null=True, verbose_name='MAX ID')
    email = models.EmailField(blank=True, null=True, verbose_name='E-mail')
    time_created = models.DateTimeField(auto_now_add=True, verbose_name='Дата создания')
    time_updated = models.DateTimeField(auto_now=True, verbose_name='Дата изменения')


    def __str__(self):
        return f'{self.first_name} {self.last_name}'

    class Meta:
        verbose_name = 'Пользователь'
        verbose_name_plural = 'Пользователи'

class UserPhone(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='phones',
    )
    phone = CharField(
        max_length=20,
        blank=True, )

    class Meta:
        verbose_name = "Телефон"
        verbose_name_plural = "Телефоны"
        constraints = [
            models.UniqueConstraint(fields=["phone"], name="uniq_user_phone"),
        ]



class Address(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="addresses",
        verbose_name="Пользователь",
    )

    is_default = models.BooleanField(
        default=False,
        verbose_name="Адрес по умолчанию",
    )

    label = models.CharField(
        max_length=50,
        blank=True,
        verbose_name="Название адреса",
        help_text="Например: Дом, Офис",
    )

    recipient_name = models.CharField(
        max_length=120,
        blank=True,
        verbose_name="Получатель",
    )

    recipient_phone = models.CharField(
        max_length=32,
        blank=True,
        verbose_name="Телефон получателя",
        null=True
    )

    country = models.CharField(
        max_length=80,
        default="Россия",
        verbose_name="Страна",
    )

    city = models.CharField(
        max_length=120,
        verbose_name="Город",
    )

    street = models.CharField(
        max_length=255,
        verbose_name="Улица",
    )

    house = models.CharField(
        max_length=50,
        verbose_name="Дом",
    )

    apartment = models.CharField(
        max_length=50,
        blank=True,
        verbose_name="Квартира / офис",
    )

    postcode = models.CharField(
        max_length=20,
        blank=True,
        verbose_name="Почтовый индекс",
    )

    comment = models.TextField(
        blank=True,
        verbose_name="Комментарий для курьера",
        help_text="Подъезд, этаж, код домофона и т.п.",
    )

    delivery_address_text = models.TextField(max_length=455, blank=True, verbose_name="Адрес доставки полный")

    # ПВЗ/самовывоз: хранить идентификаторы (адрес получателя всё равно в Address)
    pickup_point_code = models.CharField(max_length=120, blank=True)
    pickup_point_address = models.CharField(max_length=255, blank=True)
    pickup_point_provider = models.CharField(max_length=50, blank=True)

    time_created = models.DateTimeField(
        auto_now_add=True,
        verbose_name="Дата создания",
    )

    time_updated = models.DateTimeField(
        auto_now=True,
        verbose_name="Дата изменения",
    )

    class Meta:
        verbose_name = "Адрес доставки"
        verbose_name_plural = "Адреса доставки"
        ordering = ("-is_default", "-time_created")

    def __str__(self):
        base = f"{self.city}, {self.street}, {self.house}"
        if self.apartment:
            base += f", {self.apartment}"
        return base


class Requisites(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
    )
    company_name = models.CharField(max_length=255, verbose_name='Наименование')
    inn = models.CharField(max_length=20, blank=True, verbose_name="ИНН")
    kpp = models.CharField(max_length=20, blank=True, verbose_name="КПП")

    bik = models.CharField(max_length=20, blank=True, verbose_name="БИК")
    legal_address = models.CharField(max_length=255, blank=True, verbose_name="Юридический адрес")
    settlement_account = models.CharField(max_length=40, blank=True, verbose_name="Расчётный счёт")

    is_default = models.BooleanField(default=False, verbose_name="По умолчанию")

    time_created = models.DateTimeField(auto_now_add=True)
    time_updated = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Реквизиты"
        verbose_name_plural = "Реквизиты"
        constraints = [
            models.UniqueConstraint(fields=["user", "inn", "settlement_account"], name="uniq_user_inn_rs"),
        ]

    def __str__(self):
        return f"{self.company_name} (ИНН {self.inn})"


