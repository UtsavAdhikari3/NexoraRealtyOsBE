from django.conf import settings
from django.core.management.base import BaseCommand

from crm_inbox.models import WebhookEvent
from crm_inbox.services import process_webhook_event
from operations.scheduler import scheduled_job


class Command(BaseCommand):
    help = "Retry Meta webhook events that failed during initial processing."

    def handle(self, *args, **options):
        with scheduled_job("meta-webhook-retry", lease_seconds=300) as job:
            if not job.claimed:
                self.stdout.write("Meta webhook retry is already running; skipped.")
                return

            events = WebhookEvent.objects.filter(
                status=WebhookEvent.STATUS_FAILED,
                attempts__lt=settings.META_WEBHOOK_MAX_RETRY_ATTEMPTS,
            ).order_by("received_at")[:100]
            processed = 0
            failed = 0
            for event in events:
                process_webhook_event(event)
                if event.status == WebhookEvent.STATUS_PROCESSED:
                    processed += 1
                else:
                    failed += 1
            job.result = {"processed": processed, "failed": failed}
            self.stdout.write(
                self.style.SUCCESS(
                    f"Retried {processed + failed} Meta webhook event(s); "
                    f"{processed} processed, {failed} still failed."
                )
            )
