from django.core.management.base import BaseCommand

from properties.freshness import process_listing_freshness


class Command(BaseCommand):
    help = "Send listing reconfirmation reminders and hide expired listings."

    def handle(self, *args, **options):
        count = process_listing_freshness()
        self.stdout.write(self.style.SUCCESS(f"Created {count} listing freshness notification(s)."))
