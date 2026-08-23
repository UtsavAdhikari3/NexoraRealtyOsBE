from django.db import migrations


def normalize_phone_numbers(apps, schema_editor):
    from agencies.phone import is_valid_nepal_phone, normalize_nepal_phone

    AgencyUser = apps.get_model("users", "AgencyUser")
    changed = []
    for user in AgencyUser.objects.exclude(phone__isnull=True).exclude(phone="").iterator():
        if is_valid_nepal_phone(user.phone):
            normalized = normalize_nepal_phone(user.phone)
            if normalized != user.phone:
                user.phone = normalized
                changed.append(user)
    if changed:
        AgencyUser.objects.bulk_update(changed, ["phone"], batch_size=500)


class Migration(migrations.Migration):
    dependencies = [("users", "0009_normalize_email_case")]
    operations = [migrations.RunPython(normalize_phone_numbers, migrations.RunPython.noop)]
