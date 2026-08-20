from django.db import migrations, models
import django.db.models.deletion


def migrate_legacy_images(apps, schema_editor):
    SocialPost = apps.get_model("social_media", "SocialPost")
    SocialPostMedia = apps.get_model("social_media", "SocialPostMedia")

    media_rows = [
        SocialPostMedia(post_id=post.id, image=post.image, position=0)
        for post in SocialPost.objects.exclude(image="").exclude(image__isnull=True)
    ]
    SocialPostMedia.objects.bulk_create(media_rows, ignore_conflicts=True)


class Migration(migrations.Migration):
    dependencies = [
        ("social_media", "0007_socialaccount_user_access_token"),
    ]

    operations = [
        migrations.CreateModel(
            name="SocialPostMedia",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("image", models.ImageField(upload_to="social_posts/")),
                ("position", models.PositiveSmallIntegerField()),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "post",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="media_items",
                        to="social_media.socialpost",
                    ),
                ),
            ],
            options={"ordering": ["position", "id"]},
        ),
        migrations.AddConstraint(
            model_name="socialpostmedia",
            constraint=models.CheckConstraint(
                condition=models.Q(position__lt=5),
                name="social_post_media_position_below_limit",
            ),
        ),
        migrations.RunPython(migrate_legacy_images, migrations.RunPython.noop),
    ]
