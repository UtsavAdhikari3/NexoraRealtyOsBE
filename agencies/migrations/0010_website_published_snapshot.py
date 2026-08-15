from django.db import migrations, models


def copy_existing_published_config(apps, schema_editor):
    Agency = apps.get_model("agencies", "Agency")
    for agency in Agency.objects.all().iterator():
        published = dict(agency.website_config or {})
        published.update({
            "schema_version": 2,
            "primary_color": agency.primary_color or published.get("primary_color") or "#496B5A",
            "about": agency.about or published.get("about", ""),
            "public_email": agency.email or published.get("public_email", ""),
            "public_phone": agency.phone or published.get("public_phone", ""),
            "address": agency.address or published.get("address", ""),
            "business_hours": agency.business_hours or published.get("business_hours", ""),
            "facebook_url": agency.facebook_url or published.get("facebook_url", ""),
            "instagram_url": agency.instagram_url or published.get("instagram_url", ""),
            "linkedin_url": agency.linkedin_url or published.get("linkedin_url", ""),
            "youtube_url": agency.youtube_url or published.get("youtube_url", ""),
            "tiktok_url": agency.tiktok_url or published.get("tiktok_url", ""),
            "whatsapp_number": agency.whatsapp_number or published.get("whatsapp_number", ""),
            "viber_number": agency.viber_number or published.get("viber_number", ""),
            "seo_title": agency.seo_title or published.get("seo_title", ""),
            "seo_description": agency.seo_description or published.get("seo_description", ""),
        })
        media = dict(published.get("media") or {})
        if agency.logo:
            media["logo"] = str(agency.logo)
        if agency.cover_image:
            media["hero_image"] = str(agency.cover_image)
        published["media"] = media
        agency.website_published_config = published if agency.is_website_published else {}
        agency.website_config_version = 1 if agency.is_website_published and published else 0
        agency.website_completion_percentage = 100 if agency.website_onboarding_status == "completed" else 0
        agency.save(update_fields=[
            "website_published_config", "website_config_version", "website_completion_percentage",
        ])


class Migration(migrations.Migration):
    dependencies = [("agencies", "0009_agency_website_onboarding")]

    operations = [
        migrations.AddField(
            model_name="agency",
            name="website_published_config",
            field=models.JSONField(blank=True, default=dict),
        ),
        migrations.AddField(
            model_name="agency",
            name="website_completion_percentage",
            field=models.PositiveSmallIntegerField(default=0),
        ),
        migrations.AddField(
            model_name="agency",
            name="website_config_version",
            field=models.PositiveIntegerField(default=0),
        ),
        migrations.AlterField(
            model_name="agency",
            name="website_onboarding_status",
            field=models.CharField(
                choices=[
                    ("not_started", "Not started"),
                    ("in_progress", "In progress"),
                    ("ready", "Ready to publish"),
                    ("completed", "Completed"),
                ],
                default="not_started",
                max_length=20,
            ),
        ),
        migrations.AlterField(
            model_name="agency",
            name="is_website_published",
            field=models.BooleanField(default=False),
        ),
        migrations.RunPython(copy_existing_published_config, migrations.RunPython.noop),
    ]
