import logging
from datetime import timedelta

from django.core.management.base import BaseCommand
from django.db.models import Q
from django.utils import timezone

from leads.emails import send_follow_up_reminder
from leads.models import Lead
from leads.automation import get_automation_settings
from operations.scheduler import scheduled_job
from site_visits.emails import send_site_visit_reminder
from site_visits.models import SiteVisit

logger = logging.getLogger(__name__)


def _send_each(ids, sender, label):
    sent = failed = 0
    for object_id in ids:
        try:
            sent += int(bool(sender(object_id)))
        except Exception:
            failed += 1
            logger.exception("%s reminder failed for id %s", label, object_id)
    return sent, failed


class Command(BaseCommand):
    help = "Send due lead follow-up and upcoming site-visit reminders idempotently."

    def add_arguments(self, parser):
        parser.add_argument("--hours", type=int, default=24)

    def handle(self, *args, **options):
        with scheduled_job("lead-and-visit-reminders") as job:
            if not job.claimed:
                self.stdout.write("Skipped due reminders; another worker holds the lease.")
                return
            now = timezone.now()
            window_end = now + timedelta(hours=options["hours"])

            lead_candidates = Lead.objects.filter(
                follow_up_status=Lead.FOLLOW_UP_PENDING,
                next_follow_up_at__isnull=False,
                follow_up_reminder_sent_at__isnull=True,
                agency__is_active=True,
                agency__payment_status="paid",
            ).filter(
                Q(agency__subscription_expires_at__isnull=True)
                | Q(agency__subscription_expires_at__gt=now)
            ).select_related("agency")
            lead_ids = []
            settings_cache = {}
            for lead in lead_candidates:
                automation_settings = settings_cache.get(lead.agency_id)
                if automation_settings is None:
                    automation_settings = get_automation_settings(lead.agency)
                    settings_cache[lead.agency_id] = automation_settings
                if automation_settings.is_enabled and lead.next_follow_up_at <= now + timedelta(
                    hours=automation_settings.follow_up_reminder_hours
                ):
                    lead_ids.append(lead.id)

            visit_ids = SiteVisit.objects.filter(
                status__in=["scheduled", "rescheduled"],
                scheduled_at__gte=now,
                scheduled_at__lte=window_end,
                reminder_sent_at__isnull=True,
                agency__is_active=True,
                agency__payment_status="paid",
            ).filter(
                Q(agency__subscription_expires_at__isnull=True)
                | Q(agency__subscription_expires_at__gt=now)
            ).values_list("id", flat=True)

            lead_sent, lead_failed = _send_each(
                lead_ids, send_follow_up_reminder, "Lead follow-up"
            )
            visit_sent, visit_failed = _send_each(
                visit_ids, send_site_visit_reminder, "Site visit"
            )
            job.result = {
                "lead_sent": lead_sent,
                "lead_failed": lead_failed,
                "visit_sent": visit_sent,
                "visit_failed": visit_failed,
            }

        self.stdout.write(
            self.style.SUCCESS(
                f"Sent {lead_sent} follow-up reminder(s) and "
                f"{visit_sent} site-visit reminder(s)."
            )
        )
