import uuid

from django.db import migrations, models
import django.db.models.deletion


def backfill_legacy_domains(apps, schema_editor):
    Agency = apps.get_model("agencies", "Agency")
    AgencyDomain = apps.get_model("agencies", "AgencyDomain")
    for agency in Agency.objects.exclude(custom_domain="").iterator():
        domain = (agency.custom_domain or "").strip().lower().rstrip(".")
        if domain:
            AgencyDomain.objects.get_or_create(
                domain=domain,
                defaults={"agency": agency, "status": "pending"},
            )


class Migration(migrations.Migration):
    dependencies = [("agencies", "0014_normalize_template_capabilities")]
    operations = [
        migrations.CreateModel(
            name="AgencyDomain",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("domain", models.CharField(max_length=253, unique=True)),
                ("status", models.CharField(choices=[("pending", "Pending verification"), ("verified", "Verified"), ("failed", "Verification failed")], default="pending", max_length=16)),
                ("verification_token", models.UUIDField(default=uuid.uuid4, editable=False, unique=True)),
                ("is_active", models.BooleanField(default=False)),
                ("is_primary", models.BooleanField(default=False)),
                ("verified_at", models.DateTimeField(blank=True, null=True)),
                ("last_checked_at", models.DateTimeField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("agency", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="website_domains", to="agencies.agency")),
            ],
            options={"ordering": ["-is_primary", "domain"]},
        ),
        migrations.AddConstraint(
            model_name="agencydomain",
            constraint=models.UniqueConstraint(condition=models.Q(("is_primary", True)), fields=("agency",), name="unique_primary_domain_per_agency"),
        ),
        migrations.AddIndex(
            model_name="agencydomain",
            index=models.Index(fields=["domain", "status", "is_active"], name="agency_domain_lookup_idx"),
        ),
        migrations.RunPython(backfill_legacy_domains, migrations.RunPython.noop),
    ]
