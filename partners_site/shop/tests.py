import json
import tempfile
from io import BytesIO

from django.contrib import admin
from django.core.exceptions import ValidationError
from django.core.files.base import ContentFile
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import IntegrityError, transaction
from django.test import RequestFactory, TestCase
from django.test import override_settings
from django.urls import reverse
from PIL import Image as PilImage

from orders.models import Cart, CartItem, Order, OrderItem
from users.models import Customer, User

from .admin import RelatedProductStatsAdmin
from .discounts import get_category_discount_limit, get_item_discount_percent
from .models import (
    Category,
    CategoryStatusDiscountCap,
    Image,
    Instruction,
    Product,
    ProductGroup,
    RelatedProductGroup,
    RelatedProductStats,
)
from .services import get_cart_related_product_cards


class DiscountResolverTests(TestCase):
    def test_standard_policy_uses_category_discount_limit(self):
        category = Category.objects.create(
            name="Стандарт",
            discount=20,
            discount_policy=Category.DiscountPolicy.STANDARD,
        )

        self.assertEqual(
            get_item_discount_percent(
                partner_discount=35,
                category=category,
                partner_status=Customer.PartnerStatus.Gold,
            ),
            20,
        )

    def test_status_capped_policy_uses_status_cap_limit(self):
        category = Category.objects.create(
            name="Спец",
            discount=50,
            discount_policy=Category.DiscountPolicy.STATUS_CAPPED,
        )
        CategoryStatusDiscountCap.objects.create(
            category=category,
            partner_status=Customer.PartnerStatus.Gold,
            max_discount=12,
        )

        self.assertEqual(
            get_item_discount_percent(
                partner_discount=35,
                category=category,
                partner_status=Customer.PartnerStatus.Gold,
            ),
            12,
        )
        self.assertEqual(
            get_category_discount_limit(category, Customer.PartnerStatus.Gold),
            12,
        )

    def test_status_capped_without_cap_falls_back_to_zero(self):
        category = Category.objects.create(
            name="Спец без cap",
            discount=50,
            discount_policy=Category.DiscountPolicy.STATUS_CAPPED,
        )

        self.assertEqual(
            get_item_discount_percent(
                partner_discount=35,
                category=category,
                partner_status=Customer.PartnerStatus.Gold,
            ),
            0,
        )
        self.assertEqual(
            get_category_discount_limit(category, Customer.PartnerStatus.Gold),
            0,
        )


class CatalogAndDetailDiscountTests(TestCase):
    def setUp(self):
        self.customer = Customer.objects.create(
            name="Партнер",
            partner_status=Customer.PartnerStatus.Gold,
        )
        self.user = User.objects.create_user(
            username="partner",
            password="secret",
            customer=self.customer,
        )
        self.client.force_login(self.user)

        self.category = Category.objects.create(
            name="Спец категория",
            discount=50,
            discount_policy=Category.DiscountPolicy.STATUS_CAPPED,
        )
        CategoryStatusDiscountCap.objects.create(
            category=self.category,
            partner_status=Customer.PartnerStatus.Gold,
            max_discount=12,
        )

        self.group = ProductGroup.objects.create(
            name="Группа",
            category=self.category,
        )
        self.product = Product.objects.create(
            name="Товар",
            amo_id=1001,
            price=1000,
            title="Описание",
            group=self.group,
            is_primary=True,
            is_visible=True,
        )

    def test_catalog_uses_status_capped_discount(self):
        response = self.client.get(reverse("catalog"))

        self.assertEqual(response.status_code, 200)
        cards = response.context["group_cards"]
        self.assertEqual(len(cards), 1)
        self.assertEqual(cards[0]["discount_percent"], 12)
        self.assertEqual(cards[0]["discounted_price"], 880)

    def test_catalog_search_uses_product_name_substring(self):
        matching_group = ProductGroup.objects.create(
            name="Unrelated group",
            category=self.category,
        )
        matching_product = Product.objects.create(
            name="Searchable Relay",
            amo_id=1002,
            price=1200,
            title="Description",
            group=matching_group,
            is_visible=True,
        )
        Product.objects.create(
            name="Plain Switch",
            amo_id=1004,
            price=1400,
            title="Description",
            group=matching_group,
            is_visible=True,
        )
        group_name_only = ProductGroup.objects.create(
            name="Relay group",
            category=self.category,
        )
        Product.objects.create(
            name="Different item",
            amo_id=1003,
            price=1300,
            title="Description",
            group=group_name_only,
            is_visible=True,
        )

        response = self.client.get(reverse("catalog"), {"q": "relay"})

        self.assertEqual(response.status_code, 200)
        cards = response.context["group_cards"]
        group_ids = [card["group"].id for card in cards]
        self.assertEqual(group_ids, [matching_group.id])
        self.assertEqual(cards[0]["product"].id, matching_product.id)
        self.assertEqual([m.id for m in cards[0]["mods"]], [matching_product.id])

    def test_product_detail_uses_status_capped_discount(self):
        response = self.client.get(reverse("product_group_detail", args=[self.group.pk]))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["discount_percent"], 12)
        self.assertEqual(response.context["discounted_price"], 880)

    def test_product_detail_renders_remote_instruction_url(self):
        instruction_url = (
            "https://www.hite-pro.ru/wp-content/uploads/manual/AT115x105mm.pdf"
        )
        Instruction.objects.create(
            product=self.product,
            name="Instruction",
            file_url=instruction_url,
        )

        response = self.client.get(reverse("product_group_detail", args=[self.group.pk]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, f'href="{instruction_url}"')
        instruction_items = response.context["instruction_items"]
        self.assertEqual(instruction_items[0]["file_ext"], "PDF")
        self.assertNotIn("file_size", instruction_items[0])


class ProductImageSaveTests(TestCase):
    def setUp(self):
        self.media_root = tempfile.TemporaryDirectory()
        self.override = override_settings(MEDIA_ROOT=self.media_root.name)
        self.override.enable()
        self.addCleanup(self.override.disable)
        self.addCleanup(self.media_root.cleanup)

        category = Category.objects.create(name="Category", discount=0)
        group = ProductGroup.objects.create(name="Group", category=category)
        self.product = Product.objects.create(
            name="Product",
            amo_id=2001,
            price=100,
            title="Description",
            group=group,
            is_visible=True,
        )

    @staticmethod
    def _image_bytes(format_name):
        output = BytesIO()
        PilImage.new("RGB", (20, 20), "red").save(output, format=format_name)
        return output.getvalue()

    def test_uploaded_product_image_is_saved_as_webp(self):
        image = Image(
            product=self.product,
            photo=SimpleUploadedFile(
                "photo.jpg",
                self._image_bytes("JPEG"),
                content_type="image/jpeg",
            ),
        )

        image.save()

        self.assertTrue(image.photo.name.endswith(".webp"))
        with PilImage.open(image.photo.path) as saved_image:
            self.assertEqual(saved_image.format, "WEBP")

    def test_field_file_save_is_saved_as_webp(self):
        image = Image(product=self.product, name="photo", title="photo")

        image.photo.save(
            "photo.png",
            ContentFile(self._image_bytes("PNG")),
            save=True,
        )
        image.refresh_from_db()

        self.assertTrue(image.photo.name.endswith(".webp"))
        with PilImage.open(image.photo.path) as saved_image:
            self.assertEqual(saved_image.format, "WEBP")


class RelatedProductGroupTests(TestCase):
    def setUp(self):
        self.customer = Customer.objects.create(
            name="Партнер",
            partner_discount=35,
            partner_status=Customer.PartnerStatus.Gold,
        )
        self.user = User.objects.create_user(
            username="related_partner",
            password="secret",
            customer=self.customer,
        )
        self.category = Category.objects.create(
            name="Категория",
            discount=20,
            discount_policy=Category.DiscountPolicy.STANDARD,
        )
        self.cart = Cart.objects.create(user=self.user)
        self.source_group, self.source_product = self._create_group_with_product(
            "Источник",
            1000,
        )
        CartItem.objects.create(
            cart=self.cart,
            product=self.source_product,
            qty=1,
        )

    def _create_group_with_product(
        self,
        name: str,
        price: int,
        *,
        is_visible: bool = True,
        is_primary: bool = True,
    ) -> tuple[ProductGroup, Product]:
        group = ProductGroup.objects.create(name=name, category=self.category)
        product = Product.objects.create(
            name=name,
            amo_id=abs(hash(name)) % 1000000,
            price=price,
            title="Описание",
            group=group,
            is_primary=is_primary,
            is_visible=is_visible,
        )
        return group, product

    def test_self_relation_is_invalid(self):
        relation = RelatedProductGroup(
            source_group=self.source_group,
            related_group=self.source_group,
        )

        with self.assertRaises(ValidationError):
            relation.full_clean()

    def test_duplicate_relation_is_rejected(self):
        related_group, _ = self._create_group_with_product("Связанный", 500)
        RelatedProductGroup.objects.create(
            source_group=self.source_group,
            related_group=related_group,
        )

        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                RelatedProductGroup.objects.create(
                    source_group=self.source_group,
                    related_group=related_group,
                )

    def test_related_cards_use_manual_relations(self):
        related_group, related_product = self._create_group_with_product(
            "Сопутствующий",
            1500,
        )
        RelatedProductGroup.objects.create(
            source_group=self.source_group,
            related_group=related_group,
        )

        cards = get_cart_related_product_cards(self.cart, self.user)

        self.assertEqual(len(cards), 1)
        self.assertEqual(cards[0]["group"], related_group)
        self.assertEqual(cards[0]["product"], related_product)

    def test_related_card_contains_visible_modifications(self):
        related_group, primary_product = self._create_group_with_product(
            "Related set",
            1500,
        )
        primary_product.modification_name = "Base"
        primary_product.save(update_fields=["modification_name"])
        hidden_product = Product.objects.create(
            name="Hidden modification",
            modification_name="Hidden",
            amo_id=3501,
            price=1700,
            title="Description",
            group=related_group,
            is_visible=False,
        )
        visible_product = Product.objects.create(
            name="Visible <modification>",
            modification_name="Extended",
            amo_id=3502,
            price=2000,
            title="Description",
            group=related_group,
            is_visible=True,
        )
        RelatedProductGroup.objects.create(
            source_group=self.source_group,
            related_group=related_group,
        )

        cards = get_cart_related_product_cards(self.cart, self.user)

        self.assertEqual(len(cards), 1)
        self.assertEqual(cards[0]["product"], primary_product)
        modification_ids = [
            modification["id"] for modification in cards[0]["modifications"]
        ]
        self.assertEqual(modification_ids, [primary_product.id, visible_product.id])
        self.assertNotIn(hidden_product.id, modification_ids)

        modifications_json = json.loads(cards[0]["modifications_json"])
        self.assertNotIn("<", cards[0]["modifications_json"])
        self.assertEqual(
            modifications_json[1],
            {
                "id": visible_product.id,
                "name": visible_product.name,
                "modification_name": visible_product.modification_name,
                "price": 2000,
                "discounted_price": 1600,
                "discount_percent": 20,
                "image_url": "",
            },
        )

    def test_related_cards_exclude_products_already_in_cart(self):
        related_group, related_product = self._create_group_with_product(
            "Уже в корзине",
            1500,
        )
        CartItem.objects.create(cart=self.cart, product=related_product, qty=1)
        RelatedProductGroup.objects.create(
            source_group=self.source_group,
            related_group=related_group,
        )

        cards = get_cart_related_product_cards(self.cart, self.user)

        self.assertEqual(cards, [])

    def test_related_cards_ignore_groups_without_visible_products(self):
        related_group, _ = self._create_group_with_product(
            "Скрытый",
            1500,
            is_visible=False,
        )
        RelatedProductGroup.objects.create(
            source_group=self.source_group,
            related_group=related_group,
        )

        cards = get_cart_related_product_cards(self.cart, self.user)

        self.assertEqual(cards, [])

    def test_related_cards_are_deduplicated_and_ordered(self):
        second_source_group, second_source_product = self._create_group_with_product(
            "Второй источник",
            2000,
        )
        CartItem.objects.create(
            cart=self.cart,
            product=second_source_product,
            qty=1,
        )
        first_group, _ = self._create_group_with_product("Первый", 500)
        second_group, _ = self._create_group_with_product("Второй", 600)

        RelatedProductGroup.objects.create(
            source_group=self.source_group,
            related_group=second_group,
            sort_order=20,
        )
        RelatedProductGroup.objects.create(
            source_group=self.source_group,
            related_group=first_group,
            sort_order=10,
        )
        RelatedProductGroup.objects.create(
            source_group=second_source_group,
            related_group=first_group,
            sort_order=1,
        )

        cards = get_cart_related_product_cards(self.cart, self.user)

        self.assertEqual([card["group"] for card in cards], [first_group, second_group])

    def test_related_cards_use_partner_discount(self):
        related_group, _ = self._create_group_with_product("Со скидкой", 1000)
        RelatedProductGroup.objects.create(
            source_group=self.source_group,
            related_group=related_group,
        )

        cards = get_cart_related_product_cards(self.cart, self.user)

        self.assertEqual(cards[0]["discount_percent"], 20)
        self.assertEqual(cards[0]["discounted_price"], 800)
        self.assertTrue(cards[0]["has_discount"])


class RelatedProductStatsAdminTests(TestCase):
    def setUp(self):
        self.customer = Customer.objects.create(
            name="Партнер",
            partner_status=Customer.PartnerStatus.Gold,
        )
        self.user = User.objects.create_user(
            username="related_stats_partner",
            password="secret",
            customer=self.customer,
        )
        self.category = Category.objects.create(name="Категория", discount=0)
        self.group = ProductGroup.objects.create(
            name="Группа",
            category=self.category,
        )
        self.product = Product.objects.create(
            name="Tracked product",
            amo_id=4001,
            price=1000,
            title="Описание",
            group=self.group,
            is_visible=True,
        )
        self.untracked_product = Product.objects.create(
            name="Untracked product",
            amo_id=4002,
            price=500,
            title="Описание",
            group=self.group,
            is_visible=True,
        )
        self.model_admin = RelatedProductStatsAdmin(RelatedProductStats, admin.site)
        self.factory = RequestFactory()

    def test_admin_report_aggregates_cart_and_order_stats(self):
        cart = Cart.objects.create(user=self.user)
        CartItem.objects.create(
            cart=cart,
            product=self.product,
            qty=3,
            current_unit_price_discounted=800,
            related_added_qty=2,
        )
        CartItem.objects.create(
            cart=cart,
            product=self.untracked_product,
            qty=1,
            current_unit_price_discounted=500,
            related_added_qty=0,
        )
        order = Order.objects.create(user=self.user)
        OrderItem.objects.create(
            order=order,
            product=self.product,
            qty=2,
            current_unit_price_discounted=750,
            related_added_qty=1,
        )

        request = self.factory.get("/admin/shop/relatedproductstats/")
        stats = list(self.model_admin.get_queryset(request))

        self.assertEqual(stats, [self.product])
        self.assertEqual(stats[0].related_cart_qty, 2)
        self.assertEqual(stats[0].related_cart_amount, 1600)
        self.assertEqual(stats[0].related_order_qty, 1)
        self.assertEqual(stats[0].related_order_amount, 750)
