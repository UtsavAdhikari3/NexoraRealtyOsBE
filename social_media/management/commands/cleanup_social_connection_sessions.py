from django.core.management.base import BaseCommand
from django.db.models import Q
from django.utils import timezone

from operations.scheduler import scheduled_job
from social_media.models import SocialConnectionSession


class Command(BaseCommand):
    help = "Delete expired or completed Meta Page-selection sessions."

    def handle(self, *args, **options):
        with scheduled_job("social-connection-session-cleanup", lease_seconds=300) as job:
            if not job.claimed:
                self.stdout.write("Social connection cleanup is already running; skipped.")
                return
            deleted, _ = SocialConnectionSession.objects.filter(
                Q(expires_at__lte=timezone.now()) | Q(completed_at__isnull=False)
            ).delete()
            job.result = {"deleted": deleted}
            self.stdout.write(
                self.style.SUCCESS(
                    f"Deleted {deleted} expired/completed social connection session(s)."
                )
            )
