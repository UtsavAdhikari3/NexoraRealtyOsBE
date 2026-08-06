from django.db import migrations


PLANS = [
    {
        "code": "starter",
        "name": "Starter",
        "description": "For small agencies building their first digital pipeline.",
        "price_monthly": 29,
        "currency": "USD",
        "max_agents": 3,
        "max_properties": 75,
        "features": ["CRM and listings", "Public storefront", "Appointments"],
    },
    {
        "code": "growth",
        "name": "Growth",
        "description": "For growing teams that need automation and reporting.",
        "price_monthly": 79,
        "currency": "USD",
        "max_agents": 15,
        "max_properties": 500,
        "features": ["Everything in Starter", "Deals and documents", "Reports and matching", "Social inbox"],
    },
    {
        "code": "scale",
        "name": "Scale",
        "description": "For multi-team agencies with advanced controls.",
        "price_monthly": 179,
        "currency": "USD",
        "max_agents": 100,
        "max_properties": 5000,
        "features": ["Everything in Growth", "Custom pipelines", "Audit logs", "Priority support"],
    },
]


def seed_plans(apps, schema_editor):
    Plan = apps.get_model("operations", "SubscriptionPlan")
    for row in PLANS:
        Plan.objects.update_or_create(code=row["code"], defaults=row)


def remove_plans(apps, schema_editor):
    Plan = apps.get_model("operations", "SubscriptionPlan")
    Plan.objects.filter(code__in=[row["code"] for row in PLANS]).delete()


class Migration(migrations.Migration):
    dependencies = [("operations", "0002_customerprofile_password_hash_and_more")]
    operations = [migrations.RunPython(seed_plans, remove_plans)]
