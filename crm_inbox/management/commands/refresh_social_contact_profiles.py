from django.conf import settings
from django.core.management.base import BaseCommand
from django.db.models import Q
from django.utils import timezone

from crm_inbox.models import SocialContact
from crm_inbox.services import refresh_social_contact_profile
from operations.scheduler import scheduled_job
from social_media.models import SocialAccount


class Command(BaseCommand):
    help = "Refresh names, usernames, and avatars for Meta inbox contacts."

    def add_arguments(self, parser):
        parser.add_argument("--limit", type=int, default=100)
        parser.add_argument("--force", action="store_true")

    def handle(self, *args, **options):
        limit = max(1, min(options["limit"], 1000))
        force = options["force"]
        refresh_before = timezone.now() - timezone.timedelta(
            hours=settings.SOCIAL_PROFILE_REFRESH_HOURS
        )
        queryset = SocialContact.objects.select_related(
            "social_account",
            "linked_lead",
        ).filter(
            social_account__status=SocialAccount.STATUS_CONNECTED,
        )
        if not force:
            queryset = queryset.filter(
                Q(profile_synced_at__isnull=True)
                | Q(profile_synced_at__lte=refresh_before)
            )

        with scheduled_job("social-contact-profile-refresh", lease_seconds=600) as job:
            if not job.claimed:
                self.stdout.write("Social contact profile refresh is already running; skipped.")
                return
            refreshed = 0
            resolved = 0
            for contact in queryset.order_by("profile_synced_at", "id")[:limit]:
                refresh_social_contact_profile(contact, force=force)
                refreshed += 1
                if contact.display_name or contact.username:
                    resolved += 1
            job.result = {"refreshed": refreshed, "resolved": resolved}
            self.stdout.write(
                self.style.SUCCESS(
                    f"Refreshed {refreshed} social contact profile(s); {resolved} resolved."
                )
            )
