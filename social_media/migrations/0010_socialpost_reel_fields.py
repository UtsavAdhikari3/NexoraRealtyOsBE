from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("social_media", "0009_socialconnectionsession"),
    ]

    operations = [
        migrations.AddField(
            model_name="socialpost",
            name="post_format",
            field=models.CharField(
                choices=[("image", "Image post"), ("reel", "Reel")],
                default="image",
                max_length=20,
            ),
        ),
        migrations.AddField(
            model_name="socialpost",
            name="video",
            field=models.FileField(
                blank=True,
                null=True,
                upload_to="social_posts/reels/",
            ),
        ),
        migrations.AddField(
            model_name="socialpost",
            name="video_duration_seconds",
            field=models.FloatField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="socialpost",
            name="video_height",
            field=models.PositiveIntegerField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="socialpost",
            name="video_size_bytes",
            field=models.PositiveIntegerField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="socialpost",
            name="video_width",
            field=models.PositiveIntegerField(blank=True, null=True),
        ),
    ]
