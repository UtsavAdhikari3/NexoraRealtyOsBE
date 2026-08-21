from django.core.management.base import BaseCommand

from leads.automation import process_lead_automation
from operations.scheduler import scheduled_job


class Command(BaseCommand):
    help = "Escalate, alert, and reassign leads according to agency automation rules."

    def handle(self, *args, **options):
        with scheduled_job("lead-automation") as job:
            if not job.claimed:
                self.stdout.write("Skipped lead automation; another worker holds the lease.")
                return
            counts = process_lead_automation()
            job.result = counts
        self.stdout.write(self.style.SUCCESS(
            "Processed lead automation: "
            f"{counts['escalated']} escalated, "
            f"{counts['alerts']} manager alert(s), and "
            f"{counts['reassigned']} reassigned."
        ))
