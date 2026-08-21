from django.db import migrations, models


def resolve_duplicate_primary_media(apps, schema_editor):
    PropertyMedia = apps.get_model("properties", "PropertyMedia")
    duplicate_property_ids = (
        PropertyMedia.objects.filter(is_primary=True)
        .values("property_id")
        .annotate(total=models.Count("id"))
        .filter(total__gt=1)
        .values_list("property_id", flat=True)
    )
    for property_id in duplicate_property_ids.iterator():
        primary_ids = list(
            PropertyMedia.objects.filter(property_id=property_id, is_primary=True)
            .order_by("sort_order", "created_at", "id")
            .values_list("id", flat=True)
        )
        PropertyMedia.objects.filter(id__in=primary_ids[1:]).update(is_primary=False)


class Migration(migrations.Migration):
    dependencies = [("properties", "0015_alter_propertyhistory_event_type")]

    operations = [
        migrations.AddField(
            model_name="propertymedia",
            name="alt_text",
            field=models.CharField(blank=True, max_length=255),
        ),
        migrations.AddField(
            model_name="propertymedia",
            name="is_public",
            field=models.BooleanField(default=True),
        ),
        migrations.RunPython(resolve_duplicate_primary_media, migrations.RunPython.noop),
        migrations.AlterModelOptions(
            name="propertymedia",
            options={"ordering": ["-is_primary", "sort_order", "created_at"]},
        ),
        migrations.AddConstraint(
            model_name="propertymedia",
            constraint=models.UniqueConstraint(
                condition=models.Q(is_primary=True),
                fields=("property",),
                name="one_primary_media_per_property",
            ),
        ),
    ]
