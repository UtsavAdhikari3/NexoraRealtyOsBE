from django.db import migrations
from django.utils.text import slugify


RESERVED_SUBDOMAINS = {
    "admin", "api", "app", "crm", "mail", "status", "support", "template", "www",
}


def clean_generated_subdomains(apps, schema_editor):
    Agency = apps.get_model("agencies", "Agency")
    database = schema_editor.connection.alias
    agencies = list(Agency.objects.using(database).order_by("id"))
    records = []
    desired_counts = {}
    explicitly_claimed = set()

    for agency in agencies:
        old_generated = slugify(f"{agency.name}-{agency.license_number}")[:180]
        current = (agency.slug or "").strip().lower()
        is_legacy_generated = not current or current == old_generated
        desired = slugify(agency.name)[:180] if is_legacy_generated else slugify(current)[:180]
        records.append((agency.id, current, desired, is_legacy_generated))
        if is_legacy_generated:
            desired_counts[desired] = desired_counts.get(desired, 0) + 1
        else:
            explicitly_claimed.add(desired)

    targets = {}
    for agency_id, current, desired, is_legacy_generated in records:
        can_clean = (
            is_legacy_generated
            and bool(desired)
            and desired not in RESERVED_SUBDOMAINS
            and desired_counts.get(desired) == 1
            and desired not in explicitly_claimed
        )
        # Conflicting legacy agencies keep their already-unique URLs. Owners can
        # rename them deliberately later; deployment itself remains safe.
        targets[agency_id] = desired if can_clean else current

    changed_ids = [agency.id for agency in agencies if agency.slug != targets[agency.id] and targets[agency.id]]
    for agency_id in changed_ids:
        Agency.objects.using(database).filter(pk=agency_id).update(slug=f"nexora-migrating-{agency_id}")
    for agency_id in changed_ids:
        Agency.objects.using(database).filter(pk=agency_id).update(slug=targets[agency_id])


class Migration(migrations.Migration):
    dependencies = [("agencies", "0015_agency_domain")]

    operations = [
        migrations.RunPython(clean_generated_subdomains, migrations.RunPython.noop),
    ]
