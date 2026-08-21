from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("agencies", "0011_restore_website_publish_default"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name="agency",
            name="website_draft_revision",
            field=models.PositiveIntegerField(default=0),
        ),
        migrations.AddField(
            model_name="agency",
            name="website_draft_updated_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="agency",
            name="website_draft_updated_by",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="website_drafts_updated",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
    ]
