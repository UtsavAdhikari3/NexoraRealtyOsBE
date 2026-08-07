from datetime import timedelta

from django.db import migrations
from django.utils import timezone


def backfill_listing_freshness(apps, schema_editor):
    Property = apps.get_model("properties", "Property")
    now = timezone.now()
    for property_obj in Property.objects.filter(is_published=True).iterator():
        verified_at = property_obj.updated_at or now
        expires_at = verified_at + timedelta(days=30)
        property_obj.availability_verified_at = verified_at
        property_obj.listing_expires_at = expires_at
        if expires_at <= now:
            property_obj.is_published = False
            property_obj.requires_republish_approval = True
        property_obj.save(update_fields=[
            "availability_verified_at", "listing_expires_at",
            "is_published", "requires_republish_approval",
        ])


class Migration(migrations.Migration):
    dependencies = [("properties", "0012_property_availability_verified_at_and_more")]
    operations = [migrations.RunPython(backfill_listing_freshness, migrations.RunPython.noop)]
