from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("properties", "0018_property_rental_and_location_privacy")]
    operations = [
        migrations.AddIndex(
            model_name="property",
            index=models.Index(fields=["agency", "is_published", "status", "listing_expires_at"], name="property_public_expiry_idx"),
        ),
        migrations.AddIndex(
            model_name="property",
            index=models.Index(fields=["agency", "purpose", "price"], name="property_purpose_price_idx"),
        ),
        migrations.AddIndex(
            model_name="property",
            index=models.Index(fields=["agency", "is_featured", "published_at"], name="property_featured_pub_idx"),
        ),
        migrations.AddIndex(
            model_name="propertymedia",
            index=models.Index(fields=["property", "-is_primary", "sort_order"], name="property_media_order_idx"),
        ),
    ]
