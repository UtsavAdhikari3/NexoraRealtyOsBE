from copy import deepcopy

from django.db import migrations


FIELD_MAP = {
    "display_name": "name",
    "about": "about",
    "public_email": "email",
    "public_phone": "phone",
    "address": "address",
    "business_hours": "business_hours",
    "primary_color": "primary_color",
    "seo_title": "seo_title",
    "seo_description": "seo_description",
    "facebook_url": "facebook_url",
    "instagram_url": "instagram_url",
    "linkedin_url": "linkedin_url",
    "youtube_url": "youtube_url",
    "tiktok_url": "tiktok_url",
    "whatsapp_number": "whatsapp_number",
    "viber_number": "viber_number",
    "language": "default_language",
}


def snapshot_organization_defaults(apps, schema_editor):
    """Preserve today's visible values before website drafts become independent."""
    Agency = apps.get_model("agencies", "Agency")
    database = schema_editor.connection.alias

    for agency in Agency.objects.using(database).iterator():
        updates = {}
        for field in ("website_draft_config", "website_published_config", "website_config"):
            existing = getattr(agency, field) or {}
            if field != "website_draft_config" and not existing:
                continue
            config = deepcopy(existing)
            for config_field, agency_field in FIELD_MAP.items():
                value = getattr(agency, agency_field, "") or ""
                if not config.get(config_field) and value:
                    config[config_field] = value

            media = dict(config.get("media") or {})
            if agency.logo and not media.get("logo"):
                media["logo"] = agency.logo.name
            if agency.cover_image and not media.get("hero_image"):
                media["hero_image"] = agency.cover_image.name
            config["media"] = media

            if config != existing:
                updates[field] = config

        if updates:
            Agency.objects.using(database).filter(pk=agency.pk).update(**updates)


class Migration(migrations.Migration):
    dependencies = [("agencies", "0016_clean_generated_subdomains")]

    operations = [
        migrations.RunPython(snapshot_organization_defaults, migrations.RunPython.noop),
    ]
