from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("social_media", "0006_socialpublishresult_external_media_id"),
    ]

    operations = [
        migrations.AddField(
            model_name="socialaccount",
            name="user_access_token",
            field=models.TextField(blank=True),
        ),
    ]
