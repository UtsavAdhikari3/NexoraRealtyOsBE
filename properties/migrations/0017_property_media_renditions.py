from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("properties", "0016_property_media_public_controls")]

    operations = [
        migrations.AddField(
            model_name="propertymedia",
            name="card_image",
            field=models.ImageField(blank=True, null=True, upload_to="property_media/renditions/card/"),
        ),
        migrations.AddField(model_name="propertymedia", name="card_width", field=models.PositiveIntegerField(blank=True, null=True)),
        migrations.AddField(model_name="propertymedia", name="card_height", field=models.PositiveIntegerField(blank=True, null=True)),
        migrations.AddField(
            model_name="propertymedia",
            name="large_image",
            field=models.ImageField(blank=True, null=True, upload_to="property_media/renditions/large/"),
        ),
        migrations.AddField(model_name="propertymedia", name="large_width", field=models.PositiveIntegerField(blank=True, null=True)),
        migrations.AddField(model_name="propertymedia", name="large_height", field=models.PositiveIntegerField(blank=True, null=True)),
        migrations.AddField(model_name="propertymedia", name="original_width", field=models.PositiveIntegerField(blank=True, null=True)),
        migrations.AddField(model_name="propertymedia", name="original_height", field=models.PositiveIntegerField(blank=True, null=True)),
    ]
