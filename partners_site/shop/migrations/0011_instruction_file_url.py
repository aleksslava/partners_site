from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("shop", "0010_remove_video_product_video_products"),
    ]

    operations = [
        migrations.RenameField(
            model_name="instruction",
            old_name="institution",
            new_name="file_url",
        ),
        migrations.AlterField(
            model_name="instruction",
            name="file_url",
            field=models.URLField(
                max_length=500,
                verbose_name="Ссылка на инструкцию",
            ),
        ),
    ]
