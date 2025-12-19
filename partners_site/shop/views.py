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

BASE_DIR = Path(__file__).resolve().parent.parent

# Create your views here.

# shop/views.py
from django.shortcuts import render
from .models import ProductGroup


def catalog_view(request):
    q = (request.GET.get('q') or '').strip()
    tag = (request.GET.get('tag') or '').strip()

    groups = (
        ProductGroup.objects
        .filter(modifications__is_visible=True)
        .distinct()
        .select_related('category')
        .prefetch_related('modifications__images')
        .order_by('-is_pinned', 'sort_order', '-id')
    )

    if q:
        q_norm = q.lower()
        groups = groups.annotate(
            name_l=Lower("name"),
            mod_name_l=Lower("modifications__name"),
        ).filter(
            Q(name_l__contains=q_norm) |
            Q(mod_name_l__contains=q_norm)
        ).distinct()

    if tag:
        groups = groups.filter(tags__name=tag).distinct()

        # теги для быстрых фильтров (можно ограничить, чтобы не показывать "пустые")
    tags = (
        Tag.objects
        .filter(productgroup__isnull=False)  # подстрой имя модели: ProductGroup
        .distinct()
        .order_by('name')
    )

    user_discount = 0
    if request.user.is_authenticated:
        if getattr(request.user, "customer_id", None):
            user_discount = int(request.user.customer.partner_discount or 0)

    group_cards = []

    for group in groups:
        mods = [m for m in group.modifications.all() if m.is_visible]
        if not mods:
            continue

        primary = next((m for m in mods if m.is_primary), None) or mods[0]

        category_discount = int(getattr(group.category, "discount", 0) or 0)
        discount_percent = min(user_discount, category_discount)  # берём меньшую скидку

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
            "mods_json": json.dumps(mods_payload, ensure_ascii=False),  # <- для JS
        })

    return render(request, "shop/catalog.html",
                  {
                      "group_cards": group_cards,
                      "q": q,
                      "tag": tag,
                      "tags": tags,
                  })


def product_group_detail(request, pk):
    group = get_object_or_404(
        ProductGroup.objects.prefetch_related(
            'modifications__images',
            'modifications__characteristics',
            'modifications__videos',
            'modifications__instruction_set',  # если related_name не задавали
        ),
        pk=pk
    )

    modifications = group.modifications.filter(is_visible=True)

    mod_id = request.GET.get('mod')
    if mod_id:
        active_mod = modifications.filter(pk=mod_id).first()
    else:
        active_mod = None

    if active_mod is None:
        active_mod = group.primary_product

    context = {
        'group': group,
        'active_mod': active_mod,
        'modifications': modifications,
    }
    return render(request, 'product_detail.html', context)


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
