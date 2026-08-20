from django.db import migrations, models


def backfill_rent_period(apps, schema_editor):
    Property = apps.get_model("properties", "Property")
    Property.objects.filter(purpose__in=["rent", "lease"], rent_period__isnull=True).update(rent_period="month")


class Migration(migrations.Migration):
    dependencies = [("properties", "0017_property_media_renditions")]

    operations = [
        migrations.AlterField(
            model_name="property",
            name="currency",
            field=models.CharField(
                choices=[("NPR", "Nepalese Rupee"), ("USD", "US Dollar"), ("INR", "Indian Rupee")],
                default="NPR",
                max_length=10,
            ),
        ),
        migrations.AddField(
            model_name="property",
            name="rent_period",
            field=models.CharField(
                blank=True,
                choices=[("week", "Per week"), ("month", "Per month"), ("year", "Per year")],
                max_length=10,
                null=True,
            ),
        ),
        migrations.AddField(
            model_name="property",
            name="show_exact_location_publicly",
            field=models.BooleanField(default=True),
        ),
        migrations.RunPython(backfill_rent_period, migrations.RunPython.noop),
    ]
