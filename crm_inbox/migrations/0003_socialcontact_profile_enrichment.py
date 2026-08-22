from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("crm_inbox", "0002_social_referral_attribution"),
    ]

    operations = [
        migrations.AddField(
            model_name="socialcontact",
            name="profile_data",
            field=models.JSONField(blank=True, default=dict),
        ),
        migrations.AddField(
            model_name="socialcontact",
            name="profile_lookup_error",
            field=models.TextField(blank=True),
        ),
        migrations.AddField(
            model_name="socialcontact",
            name="profile_synced_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]
