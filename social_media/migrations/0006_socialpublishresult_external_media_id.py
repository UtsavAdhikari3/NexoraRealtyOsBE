from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("social_media", "0005_socialaccount_webhook_error_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="socialpublishresult",
            name="external_media_id",
            field=models.CharField(blank=True, max_length=255),
        ),
    ]
