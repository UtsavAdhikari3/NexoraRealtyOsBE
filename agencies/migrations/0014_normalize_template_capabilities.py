from copy import deepcopy

from django.db import migrations


SUPPORTED_PAGES = {"home", "properties", "agents", "about", "contact", "valuation"}
SUPPORTED_SECTIONS = {
    "hero", "featured_properties", "property_categories", "services", "statistics",
    "about", "testimonials", "agents", "faqs", "newsletter", "contact_cta",
}


def normalize(config):
    value = deepcopy(config or {})
    if not value:
        return value
    value["enabled_pages"] = {
        key: bool(enabled) if key in SUPPORTED_PAGES else False
        for key, enabled in (value.get("enabled_pages") or {}).items()
    }
    for field in ("navigation", "footer_navigation"):
        value[field] = [
            item for item in (value.get(field) or [])
            if item.get("page") in SUPPORTED_PAGES
        ]
    value["section_visibility"] = {
        key: bool(visible) if key in SUPPORTED_SECTIONS else False
        for key, visible in (value.get("section_visibility") or {}).items()
    }
    value["section_order"] = [
        key for key in (value.get("section_order") or []) if key in SUPPORTED_SECTIONS
    ]
    return value


def normalize_existing_configs(apps, schema_editor):
    Agency = apps.get_model("agencies", "Agency")
    WebsiteVersion = apps.get_model("agencies", "WebsiteVersion")
    config_fields = ("website_draft_config", "website_published_config", "website_config")
    for agency in Agency.objects.iterator():
        changed = []
        for field in config_fields:
            current = getattr(agency, field)
            updated = normalize(current)
            if updated != current:
                setattr(agency, field, updated)
                changed.append(field)
        if changed:
            agency.save(update_fields=changed)
    for version in WebsiteVersion.objects.iterator():
        updated = normalize(version.config)
        if updated != version.config:
            version.config = updated
            version.save(update_fields=["config"])


class Migration(migrations.Migration):
    dependencies = [("agencies", "0013_website_publish_history")]
    operations = [migrations.RunPython(normalize_existing_configs, migrations.RunPython.noop)]
