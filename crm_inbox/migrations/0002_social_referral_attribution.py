from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("crm_inbox", "0001_initial"),
        ("social_media", "0009_socialconnectionsession"),
    ]

    operations = [
        migrations.AddField(
            model_name="conversation",
            name="referral_data",
            field=models.JSONField(blank=True, default=dict),
        ),
        migrations.AddField(
            model_name="conversation",
            name="source_social_post",
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="attributed_conversations", to="social_media.socialpost"),
        ),
        migrations.AddField(
            model_name="socialmessage",
            name="referral_data",
            field=models.JSONField(blank=True, default=dict),
        ),
    ]
