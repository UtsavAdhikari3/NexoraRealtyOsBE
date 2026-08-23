from django.db import migrations


def normalize_phone_numbers(apps, schema_editor):
    from agencies.phone import is_valid_nepal_phone, normalize_nepal_phone

    Lead = apps.get_model("leads", "Lead")
    changed = []
    for lead in Lead.objects.all().iterator():
        if is_valid_nepal_phone(lead.phone):
            normalized = normalize_nepal_phone(lead.phone)
            if normalized != lead.phone:
                lead.phone = normalized
                changed.append(lead)
    if changed:
        Lead.objects.bulk_update(changed, ["phone"], batch_size=500)


class Migration(migrations.Migration):
    dependencies = [("leads", "0007_leadassignmentrule_leadautomationevent_and_more")]
    operations = [migrations.RunPython(normalize_phone_numbers, migrations.RunPython.noop)]
