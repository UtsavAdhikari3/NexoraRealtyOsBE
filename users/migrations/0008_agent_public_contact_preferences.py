from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("users", "0007_agencyuser_facebook_url_agencyuser_instagram_url_and_more")]

    operations = [
        migrations.AddField(
            model_name="agencyuser",
            name="show_email_publicly",
            field=models.BooleanField(default=True),
        ),
        migrations.AddField(
            model_name="agencyuser",
            name="show_phone_publicly",
            field=models.BooleanField(default=True),
        ),
    ]
