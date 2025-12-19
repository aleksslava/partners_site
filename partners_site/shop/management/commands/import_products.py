import json
import os
import urllib.request
from urllib.parse import urlparse

from django.core.files.base import ContentFile
from django.core.management.base import BaseCommand
from django.db import transaction

from shop.models import Category, ProductGroup, Product, Image, Characteristics, Instruction, Video


def download_as_contentfile(url: str) -> ContentFile:
    """Скачивает URL и возвращает ContentFile."""
    with urllib.request.urlopen(url) as resp:
        data = resp.read()
    return ContentFile(data)


def filename_from_url(url: str, fallback: str) -> str:
    path = urlparse(url).path
    name = os.path.basename(path) or fallback
    # на всякий случай обрежем query/странные символы
    return name.split("?")[0]


class Command(BaseCommand):
    help = "Import products from JSON file"

    def add_arguments(self, parser):
        parser.add_argument("json_path", type=str, help="Path to JSON file")

    @transaction.atomic
    def handle(self, *args, **options):
        json_path = options["json_path"]

        with open(json_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        # JSON может быть либо списком, либо одним объектом
        items = data if isinstance(data, list) else [data]

        created_groups = 0
        created_products = 0

        for item in items:
            group_name = item["name"].strip()
            category_name = (item.get("category") or "Без категории").strip()

            category, _ = Category.objects.get_or_create(
                name=category_name,
                defaults={"discount": 0},
            )

            # ВАЖНО: подстрой под твою модель ProductGroup
            group, group_created = ProductGroup.objects.get_or_create(
                name=group_name,
                defaults={
                    "category": category,
                    # если у ProductGroup есть поля description/title — добавь сюда
                },
            )
            if not group_created:
                # обновим категорию, если изменилась
                if group.category_id != category.id:
                    group.category = category
                    group.save(update_fields=["category"])
            else:
                created_groups += 1

            # модификации
            mods = item.get("modifications") or []
            for idx, mod in enumerate(mods):
                mod_id = int(mod["id"])
                mod_name = (mod.get("name") or "").strip()
                mod_price = mod.get("price") or 0

                # как назвать модификацию в БД:
                # вариант 1: хранить "Relay-1 220 В"
                full_name = f"{group_name} {mod_name}".strip()

                product, prod_created = Product.objects.update_or_create(
                    amo_id=mod_id,  # используем id модификации как внешний id
                    defaults={
                        "group": group,
                        "name": full_name,
                        "price": int(float(mod_price)),
                        "title": (mod.get("description") or item.get("description") or "")[:400],
                        "is_visible": True,
                        # если есть short_description — заполни тут
                        # "short_description": ...
                        # "is_primary": idx == 0  # если у тебя есть поле is_primary
                    },
                )
                if prod_created:
                    created_products += 1

                # Картинка
                image_url = mod.get("image") or item.get("image")
                if image_url:
                    # чтобы не плодить одинаковые картинки — можно проверять по url/имени
                    img_cf = download_as_contentfile(image_url)
                    img_name = filename_from_url(image_url, fallback=f"{product.amo_id}.jpg")

                    # создаём новую запись Image (можно и update_or_create по имени)
                    img_obj = Image(product=product, name=img_name, title=full_name)
                    img_obj.photo.save(img_name, img_cf, save=True)

                # Характеристики
                specs = mod.get("specifications") or {}
                for k, v in specs.items():
                    Characteristics.objects.update_or_create(
                        product=product,
                        key=str(k),
                        defaults={"value": str(v)},
                    )

                # Инструкции
                instr = mod.get("instructions") or {}
                pdf_url = instr.get("pdf")
                if pdf_url:
                    pdf_cf = download_as_contentfile(pdf_url)
                    pdf_name = filename_from_url(pdf_url, fallback=f"{product.amo_id}.pdf")
                    inst = Instruction(product=product, name=f"Инструкция {full_name}")
                    inst.institution.save(pdf_name, pdf_cf, save=True)

                # Видео (ВНИМАНИЕ)
                # В твоей модели Video.video = FileField, а в JSON ссылка (не файл).
                # Если ссылка ведёт на реальный файл — можно скачать и сохранить.
                # Если это просто короткая ссылка/стрим — лучше завести video_url.
                video_url = instr.get("video")
                if video_url:
                    # Вариант А: пропускаем
                    # pass

                    # Вариант Б: пытаемся скачать как файл (сработает только если URL отдаёт файл)
                    try:
                        vid_cf = download_as_contentfile(video_url)
                        vid_name = filename_from_url(video_url, fallback=f"{product.amo_id}.mp4")
                        vid = Video(product=product, name=f"Видео {full_name}", title=f"Видео {full_name}")
                        vid.video.save(vid_name, vid_cf, save=True)
                    except Exception:
                        # не падаем, если видео не скачивается
                        pass

        self.stdout.write(self.style.SUCCESS(
            f"Done. Created groups: {created_groups}, created/updated products: {created_products}"
        ))
