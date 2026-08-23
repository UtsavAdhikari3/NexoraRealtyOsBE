from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("social_media", "0010_socialpost_reel_fields"),
    ]

    operations = [
        migrations.AlterField(
            model_name="socialaccount",
            name="platform",
            field=models.CharField(
                choices=[
                    ("facebook", "Facebook"),
                    ("instagram", "Instagram"),
                    ("whatsapp", "WhatsApp"),
                    ("tiktok", "TikTok"),
                    ("linkedin", "LinkedIn"),
                ],
                max_length=30,
            ),
        ),
        migrations.AddField(
            model_name="socialaccount",
            name="business_account_id",
            field=models.CharField(blank=True, max_length=255, null=True),
        ),
        migrations.AddField(
            model_name="socialaccount",
            name="display_phone_number",
            field=models.CharField(blank=True, max_length=50),
        ),
        migrations.AddField(
            model_name="socialaccount",
            name="phone_number_id",
            field=models.CharField(blank=True, max_length=255, null=True),
        ),
        migrations.AddField(
            model_name="socialaccount",
            name="quality_rating",
            field=models.CharField(blank=True, max_length=30),
        ),
        migrations.AlterField(
            model_name="socialpublishresult",
            name="platform",
            field=models.CharField(
                choices=[
                    ("facebook", "Facebook"),
                    ("instagram", "Instagram"),
                ],
                max_length=30,
            ),
        ),
    ]
