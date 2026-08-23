from django.db import migrations


def normalize_phone_numbers(apps, schema_editor):
    from agencies.phone import is_valid_nepal_phone, normalize_nepal_phone

    Agency = apps.get_model("agencies", "Agency")
    changed = []
    fields = ("phone", "whatsapp_number", "viber_number")
    config_fields = ("website_config", "website_draft_config", "website_published_config")
    for agency in Agency.objects.all().iterator():
        updated = False
        for field in fields:
            value = getattr(agency, field)
            if value and is_valid_nepal_phone(value):
                normalized = normalize_nepal_phone(value)
                if normalized != value:
                    setattr(agency, field, normalized)
                    updated = True
        for config_field in config_fields:
            config = getattr(agency, config_field)
            if not isinstance(config, dict):
                continue
            for key in ("public_phone", "whatsapp_number", "viber_number"):
                value = config.get(key)
                if value and is_valid_nepal_phone(value):
                    normalized = normalize_nepal_phone(value)
                    if normalized != value:
                        config[key] = normalized
                        updated = True
        if updated:
            changed.append(agency)
    if changed:
        Agency.objects.bulk_update(changed, [*fields, *config_fields], batch_size=500)


class Migration(migrations.Migration):
    dependencies = [("agencies", "0017_separate_organization_and_website_content")]
    operations = [migrations.RunPython(normalize_phone_numbers, migrations.RunPython.noop)]
