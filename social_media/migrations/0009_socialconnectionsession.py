import secrets

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("agencies", "0015_agency_domain"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("social_media", "0008_socialpostmedia"),
    ]

    operations = [
        migrations.CreateModel(
            name="SocialConnectionSession",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("token", models.CharField(default=secrets.token_urlsafe, max_length=255, unique=True)),
                ("provider", models.CharField(default="meta", max_length=30)),
                ("candidate_pages", models.JSONField(blank=True, default=list)),
                ("user_access_token", models.TextField(blank=True)),
                ("expires_at", models.DateTimeField()),
                ("completed_at", models.DateTimeField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("agency", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="social_connection_sessions", to="agencies.agency")),
                ("user", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="social_connection_sessions", to=settings.AUTH_USER_MODEL)),
            ],
        ),
    ]
