from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path

from django.contrib.auth.decorators import login_required
from django.http import HttpResponse, JsonResponse
from django.shortcuts import render, get_object_or_404
from django.template.loader import render_to_string
from django.views.generic import DetailView
from django.db.models import Q
from django.db.models.functions import Lower
import json

from taggit.models import Tag

from shop.models import Product, ProductGroup
from users.models import User

BASE_DIR = Path(__file__).resolve().parent.parent

# Create your views here.

# shop/views.py
from django.shortcuts import render
from .models import ProductGroup


from django.db.models import Q, F
from django.db.models.functions import Lower
import json
from decimal import Decimal, ROUND_HALF_UP

def catalog_view(request):
    q = (request.GET.get('q') or '').strip()
    tag = (request.GET.get('tag') or '').strip()

    user = request.user
    customer = None
    if request.user.is_authenticated:
        user = (
            User.objects
            .select_related('customer')
            .filter(pk=request.user.pk)
            .first()
            or request.user
        )
        customer = getattr(user, "customer", None)

    # Начинаем с группы товаров
    groups = ProductGroup.objects.filter(modifications__is_visible=True).distinct().select_related('category')

    # Фильтрация по поисковому запросу
    if q:
        q_norm = q.lower()
        # Фильтруем по группам и товарам
        groups = groups.annotate(
            name_l=Lower("name")
        ).filter(
            Q(name_l__contains=q_norm)
        ).distinct()

    # Фильтрация по тегам
    if tag:
        groups = groups.filter(tags__name=tag).distinct()

    # Явная сортировка каталога по позиции в модели ProductGroup
    groups = groups.order_by("sort_order", "id")

    # Получаем список всех тегов для быстрого фильтра
    tags = (
        Tag.objects
        .filter(productgroup__isnull=False)
        .distinct()
        .order_by('name')
    )

    # Получаем скидку пользователя (если он авторизован)
    user_discount = int(customer.partner_discount or 0) if customer else 0

    group_cards = []

    for group in groups:
        # Получаем все модификации группы
        mods = [m for m in group.modifications.all() if m.is_visible]
        if not mods:
            continue

        primary = next((m for m in mods if m.is_primary), None) or mods[0]

        category_discount = int(getattr(group.category, "discount", 0) or 0)
        discount_percent = min(user_discount, category_discount)  # берём меньшую скидку

        # Функция для вычисления скидки на товар
        def calc_discounted(price: int) -> int:
            p = Decimal(price)
            d = Decimal(100 - discount_percent) / Decimal(100)
            return int((p * d).quantize(Decimal("1"), rounding=ROUND_HALF_UP))

        mods_payload = []
        for m in mods:
            img = m.images.first()
            mods_payload.append({
                "id": m.id,
                "name": m.name,
                "price": m.price,
                "discount_percent": discount_percent,
                "discounted_price": calc_discounted(m.price),
                "short_description": m.short_description or "",
                "title": m.title or "",
                "image_url": img.photo.url if img else "",
            })

        group_cards.append({
            "group": group,
            "product": primary,
            "mods": mods,  # <- для <select>
            "price": primary.price,
            "discounted_price": calc_discounted(primary.price),
            "discount_percent": discount_percent,
            "has_discount": discount_percent > 0,
            "mods_json": json.dumps(mods_payload, ensure_ascii=False),  # <- для JS
        })

    # Отправляем данные в шаблон
    return render(request, "shop/catalog.html", {
        "group_cards": group_cards,
        "q": q,
        "tag": tag,
        "tags": tags,
        "user": user,
        "customer": customer,
    })



def product_group_detail(request, pk):
    group = get_object_or_404(
        ProductGroup.objects.prefetch_related(
            'modifications__images',
            'modifications__characteristics',
            'modifications__videos',
            'modifications__instructions',
        ),
        pk=pk
    )

    modifications = list(group.modifications.filter(is_visible=True))

    mod_id = request.GET.get('mod')
    if mod_id:
        active_mod = next((m for m in modifications if str(m.pk) == str(mod_id)), None)
    else:
        active_mod = None

    if active_mod is None:
        active_mod = group.primary_product

    ordered_modifications = []
    if active_mod:
        ordered_modifications.append(active_mod)
    ordered_modifications.extend(m for m in modifications if not active_mod or m.pk != active_mod.pk)

    images = []
    seen_image_ids = set()
    for mod in ordered_modifications:
        for image in mod.images.all():
            if image.pk in seen_image_ids:
                continue
            seen_image_ids.add(image.pk)
            images.append(image)

    context = {
        'group': group,
        'product': active_mod,
        'images': images,
        'instructions': active_mod.instructions.all(),
        'videos': active_mod.videos.all(),
        'mods': modifications,
        'characteristics': active_mod.characteristics.all(),
    }
    return render(request, 'shop/product_group_detail.html', context)


def product_group_api(request, pk):
    group = get_object_or_404(ProductGroup, pk=pk)
    modifications = group.modifications.filter(is_visible=True).prefetch_related('images')

    mods_payload = []
    for mod in modifications:
        mods_payload.append({
            'id': mod.id,
            'name': mod.name,
            'price': mod.price,
            'short_description': mod.short_description,
            'title': mod.title,
            'images': [img.photo.url for img in mod.images.all()],
        })

    data = {
        'id': group.id,
        'name': group.name,
        'category': group.category.name if group.category else None,
        'modifications': mods_payload,
        'primary_id': group.primary_product.id if group.primary_product else None,
    }
    return JsonResponse(data)



