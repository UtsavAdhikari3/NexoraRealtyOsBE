from django.db import migrations, models
from django.db.models.functions import Lower


def normalize_existing_emails(apps, schema_editor):
    AgencyUser = apps.get_model("users", "AgencyUser")
    database = schema_editor.connection.alias
    seen = {}

    for user in AgencyUser.objects.using(database).order_by("id").only("id", "email"):
        normalized = user.email.strip().lower()
        existing_id = seen.get(normalized)
        if existing_id is not None:
            raise RuntimeError(
                "Cannot normalize user emails because accounts "
                f"#{existing_id} and #{user.id} differ only by capitalization. "
                "Resolve the duplicate accounts before running this migration."
            )
        seen[normalized] = user.id
        if user.email != normalized:
            AgencyUser.objects.using(database).filter(pk=user.pk).update(email=normalized)


class Migration(migrations.Migration):
    dependencies = [("users", "0008_agent_public_contact_preferences")]

    operations = [
        migrations.RunPython(normalize_existing_emails, migrations.RunPython.noop),
        migrations.AddConstraint(
            model_name="agencyuser",
            constraint=models.UniqueConstraint(
                Lower("email"),
                name="users_agencyuser_email_ci_unique",
            ),
        ),
    ]
