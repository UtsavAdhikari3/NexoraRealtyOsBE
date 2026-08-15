from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("agencies", "0010_website_published_snapshot")]

    operations = [
        migrations.AlterField(
            model_name="agency",
            name="is_website_published",
            field=models.BooleanField(default=True),
        ),
    ]
