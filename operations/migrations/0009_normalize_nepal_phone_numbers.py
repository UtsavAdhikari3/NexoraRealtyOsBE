from django.db import migrations


def normalize_phone_numbers(apps, schema_editor):
    from agencies.phone import is_valid_nepal_phone, normalize_nepal_phone

    for model_name in ("Contact", "Owner", "CustomerProfile", "PublicSubmission", "Appointment"):
        Model = apps.get_model("operations", model_name)
        changed = []
        for item in Model.objects.exclude(phone="").iterator():
            if is_valid_nepal_phone(item.phone):
                normalized = normalize_nepal_phone(item.phone)
                if normalized != item.phone:
                    item.phone = normalized
                    changed.append(item)
        if changed:
            Model.objects.bulk_update(changed, ["phone"], batch_size=500)


class Migration(migrations.Migration):
    dependencies = [("operations", "0008_scheduledjob_savedsearch_last_check_error_and_more")]
    operations = [migrations.RunPython(normalize_phone_numbers, migrations.RunPython.noop)]
