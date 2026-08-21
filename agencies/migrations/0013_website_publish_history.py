from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


def backfill_published_versions(apps, schema_editor):
    Agency = apps.get_model("agencies", "Agency")
    WebsiteVersion = apps.get_model("agencies", "WebsiteVersion")
    for agency in Agency.objects.filter(is_website_published=True).iterator():
        config = agency.website_published_config or agency.website_config or {}
        if not config:
            continue
        version = agency.website_config_version or 1
        if not agency.website_published_config:
            agency.website_published_config = config
        if not agency.website_config_version:
            agency.website_config_version = version
        agency.save(update_fields=["website_published_config", "website_config_version"])
        version_row, created = WebsiteVersion.objects.get_or_create(
            agency_id=agency.id,
            version=version,
            defaults={
                "template_key": agency.website_template,
                "schema_version": config.get("schema_version", 2),
                "config": config,
            },
        )
        if created and agency.website_published_at:
            WebsiteVersion.objects.filter(pk=version_row.pk).update(published_at=agency.website_published_at)


class Migration(migrations.Migration):
    dependencies = [
        ("agencies", "0012_website_draft_revision"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="WebsiteVersion",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("version", models.PositiveIntegerField()),
                ("template_key", models.CharField(max_length=80)),
                ("schema_version", models.PositiveIntegerField(default=2)),
                ("config", models.JSONField()),
                ("published_at", models.DateTimeField(auto_now_add=True)),
                ("agency", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="website_versions", to="agencies.agency")),
                ("published_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="website_versions_published", to=settings.AUTH_USER_MODEL)),
                ("restored_from", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="restored_versions", to="agencies.websiteversion")),
            ],
            options={"ordering": ["-version"]},
        ),
        migrations.AddConstraint(
            model_name="websiteversion",
            constraint=models.UniqueConstraint(fields=("agency", "version"), name="unique_agency_website_version"),
        ),
        migrations.RunPython(backfill_published_versions, migrations.RunPython.noop),
    ]
