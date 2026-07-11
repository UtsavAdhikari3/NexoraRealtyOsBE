from datetime import timedelta

from django.core.management.base import BaseCommand
from django.db.models import Q
from django.utils import timezone

from leads.emails import send_follow_up_reminder
from leads.models import Lead
from site_visits.emails import send_site_visit_reminder
from site_visits.models import SiteVisit


class Command(BaseCommand):
    help = "Send due lead follow-up and upcoming site-visit reminders idempotently."

    def add_arguments(self, parser):
        parser.add_argument("--hours", type=int, default=24)

    def handle(self, *args, **options):
        now = timezone.now()
        window_end = now + timedelta(hours=options["hours"])

        lead_ids = Lead.objects.filter(
            follow_up_status=Lead.FOLLOW_UP_PENDING,
            next_follow_up_at__lte=window_end,
            follow_up_reminder_sent_at__isnull=True,
            agency__is_active=True,
            agency__payment_status="paid",
        ).filter(
            Q(agency__subscription_expires_at__isnull=True)
            | Q(agency__subscription_expires_at__gt=now)
        ).values_list("id", flat=True)

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

        lead_sent = sum(bool(send_follow_up_reminder(pk)) for pk in lead_ids)
        visit_sent = sum(bool(send_site_visit_reminder(pk)) for pk in visit_ids)

        self.stdout.write(
            self.style.SUCCESS(
                f"Sent {lead_sent} follow-up reminder(s) and "
                f"{visit_sent} site-visit reminder(s)."
            )
        )
