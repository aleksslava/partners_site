from __future__ import annotations

import json
from decimal import Decimal, ROUND_HALF_UP
from typing import TYPE_CHECKING, TypedDict

from django.db.models import Prefetch

from shop.discounts import get_item_discount_percent
from shop.models import Image, Product, ProductGroup, RelatedProductGroup
from users.models import User

if TYPE_CHECKING:
    from orders.models import Cart

JSON_SCRIPT_ESCAPES = str.maketrans({
    "&": "\\u0026",
    "<": "\\u003C",
    ">": "\\u003E",
})


class RelatedProductCard(TypedDict):
    """Template-ready related product card data."""

    group: ProductGroup
    product: Product
    image_url: str
    price: int
    discounted_price: int
    discount_percent: int
    has_discount: bool
    modifications: list[dict[str, int | str]]
    modifications_json: str


def _calculate_discounted_price(price: int, discount_percent: int) -> int:
    """Calculate rounded discounted product price."""
    if discount_percent <= 0:
        return price

    discount_multiplier = Decimal(100 - discount_percent) / Decimal(100)
    return int(
        (Decimal(price) * discount_multiplier).quantize(
            Decimal("1"),
            rounding=ROUND_HALF_UP,
        )
    )


def _get_primary_visible_product(products: list[Product]) -> Product | None:
    """Return the primary visible product or the first visible product."""
    primary_product = next(
        (product for product in products if product.is_primary),
        None,
    )
    return primary_product or (products[0] if products else None)


def _get_first_image_url(product: Product) -> str:
    """Return first prefetched image URL for a product."""
    image = next(iter(product.images.all()), None)
    return image.photo.url if image else ""


def _build_related_modification_payload(
    product: Product,
    discount_percent: int,
) -> dict[str, int | str]:
    """Build JSON-ready product modification data."""
    price = int(product.price or 0)
    image_url = _get_first_image_url(product)
    return {
        "id": int(product.id),
        "name": product.name,
        "modification_name": product.modification_name,
        "price": price,
        "discounted_price": _calculate_discounted_price(price, discount_percent),
        "discount_percent": discount_percent,
        "image_url": image_url,
    }


def _serialize_json_script_payload(data: object) -> str:
    """Serialize JSON data for safe embedding in a script tag."""
    return json.dumps(data, ensure_ascii=False).translate(JSON_SCRIPT_ESCAPES)


def get_cart_related_product_cards(
    cart: Cart,
    user: User,
    limit: int = 8,
) -> list[RelatedProductCard]:
    """Build related product cards for the active cart.

    Args:
        cart: Cart used as the recommendation source.
        user: Current user used for partner discount calculation.
        limit: Maximum number of cards to return.

    Returns:
        Template-ready related product cards.
    """
    if limit <= 0:
        return []

    cart_items = list(cart.items.all())
    source_group_ids = [
        item.product.group_id
        for item in cart_items
        if item.product_id and item.product.group_id
    ]
    if not source_group_ids:
        return []

    source_group_positions = {
        group_id: index
        for index, group_id in enumerate(dict.fromkeys(source_group_ids))
    }
    cart_group_ids = set(source_group_positions)

    links = (
        RelatedProductGroup.objects
        .filter(
            is_active=True,
            source_group_id__in=cart_group_ids,
            related_group__modifications__is_visible=True,
        )
        .exclude(related_group_id__in=cart_group_ids)
        .select_related("related_group", "related_group__category")
        .prefetch_related(
            "related_group__category__status_caps",
            Prefetch(
                "related_group__modifications",
                queryset=(
                    Product.objects
                    .filter(is_visible=True)
                    .order_by("id")
                    .prefetch_related(
                        Prefetch("images", queryset=Image.objects.order_by("id"))
                    )
                ),
                to_attr="visible_modifications",
            ),
        )
        .distinct()
    )
    ordered_links = sorted(
        links,
        key=lambda link: (
            source_group_positions.get(link.source_group_id, limit),
            link.sort_order,
            link.related_group_id,
            link.id,
        ),
    )

    customer = getattr(user, "customer", None)
    partner_discount = int(getattr(customer, "partner_discount", 0) or 0)
    partner_status = getattr(customer, "partner_status", None)

    cards: list[RelatedProductCard] = []
    seen_group_ids: set[int] = set()
    for link in ordered_links:
        if len(cards) >= limit:
            break
        if link.related_group_id in seen_group_ids:
            continue

        visible_products = list(
            getattr(link.related_group, "visible_modifications", [])
        )
        product = _get_primary_visible_product(visible_products)
        if product is None:
            continue

        discount_percent = get_item_discount_percent(
            partner_discount,
            link.related_group.category,
            partner_status,
        )
        price = int(product.price or 0)
        modifications = [
            _build_related_modification_payload(visible_product, discount_percent)
            for visible_product in visible_products
        ]
        cards.append({
            "group": link.related_group,
            "product": product,
            "image_url": _get_first_image_url(product),
            "price": price,
            "discounted_price": _calculate_discounted_price(price, discount_percent),
            "discount_percent": discount_percent,
            "has_discount": discount_percent > 0,
            "modifications": modifications,
            "modifications_json": _serialize_json_script_payload(modifications),
        })
        seen_group_ids.add(link.related_group_id)

    return cards
