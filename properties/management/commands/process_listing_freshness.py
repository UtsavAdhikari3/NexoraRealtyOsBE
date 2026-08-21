from django.core.management.base import BaseCommand

from properties.freshness import process_listing_freshness
from operations.scheduler import scheduled_job


class Command(BaseCommand):
    help = "Send listing reconfirmation reminders and hide expired listings."

    def handle(self, *args, **options):
        with scheduled_job("listing-freshness") as job:
            if not job.claimed:
                self.stdout.write("Skipped listing freshness; another worker holds the lease.")
                return
            count = process_listing_freshness()
            job.result = {"notifications_created": count}
        self.stdout.write(self.style.SUCCESS(f"Created {count} listing freshness notification(s)."))
