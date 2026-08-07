from django.core.management.base import BaseCommand

from leads.automation import process_lead_automation


class Command(BaseCommand):
    help = "Escalate, alert, and reassign leads according to agency automation rules."

    def handle(self, *args, **options):
        counts = process_lead_automation()
        self.stdout.write(self.style.SUCCESS(
            "Processed lead automation: "
            f"{counts['escalated']} escalated, "
            f"{counts['alerts']} manager alert(s), and "
            f"{counts['reassigned']} reassigned."
        ))
