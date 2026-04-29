import tempfile
from io import BytesIO

from django.core.files.base import ContentFile
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.test import override_settings
from django.urls import reverse
from PIL import Image as PilImage

from users.models import Customer, User

from .discounts import get_category_discount_limit, get_item_discount_percent
from .models import Category, CategoryStatusDiscountCap, Image, Product, ProductGroup


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
