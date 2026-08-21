from django.db import migrations, models


def preserve_existing_websites(apps, schema_editor):
    Agency = apps.get_model("agencies", "Agency")
    for agency in Agency.objects.filter(is_website_published=True).iterator():
        agency.website_draft_config = agency.website_config or {}
        agency.website_onboarding_status = "completed"
        agency.save(update_fields=["website_draft_config", "website_onboarding_status"])


class Migration(migrations.Migration):
    dependencies = [
        ("agencies", "0008_agency_default_date_system_agency_default_language_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="agency",
            name="website_draft_config",
            field=models.JSONField(blank=True, default=dict),
        ),
        migrations.AddField(
            model_name="agency",
            name="website_onboarding_status",
            field=models.CharField(
                choices=[
                    ("not_started", "Not started"),
                    ("in_progress", "In progress"),
                    ("completed", "Completed"),
                ],
                default="not_started",
                max_length=20,
            ),
        ),
        migrations.AddField(
            model_name="agency",
            name="website_onboarding_step",
            field=models.PositiveSmallIntegerField(default=1),
        ),
        migrations.AddField(
            model_name="agency",
            name="website_onboarding_completed_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="agency",
            name="website_published_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.RunPython(preserve_existing_websites, migrations.RunPython.noop),
    ]
