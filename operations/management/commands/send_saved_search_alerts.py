from django.conf import settings
from django.core.mail import send_mail
from django.core.management.base import BaseCommand
from django.db.models import Q
from django.utils import timezone

from operations.models import SavedSearch
from operations.scheduler import scheduled_job
from properties.models import Property


class Command(BaseCommand):
    help = "Email customers when new public properties match their saved searches."

    def handle(self, *args, **options):
        with scheduled_job("saved-search-processing") as job:
            if not job.claimed:
                self.stdout.write("Skipped saved searches; another worker holds the lease.")
                return
            sent = 0
            checked = 0
            failed = 0
            searches = SavedSearch.objects.filter(
                alerts_enabled=True,
                agency__is_active=True,
                agency__payment_status="paid",
            ).filter(
                Q(agency__subscription_expires_at__isnull=True)
                | Q(agency__subscription_expires_at__gt=timezone.now())
            ).select_related("agency", "customer")
            for saved in searches.iterator():
                checked += 1
                checked_at = timezone.now()
                try:
                    queryset = Property.objects.filter(
                        agency=saved.agency,
                        status="available",
                        is_published=True,
                        requires_republish_approval=False,
                        listing_expires_at__gt=checked_at,
                        created_at__gt=saved.last_notified_at or saved.created_at,
                    )
                    filters = saved.filters or {}
                    for exact in ["property_type", "purpose", "province", "district", "city"]:
                        if filters.get(exact):
                            queryset = queryset.filter(**{exact: filters[exact]})
                    if filters.get("price_min"):
                        queryset = queryset.filter(price__gte=filters["price_min"])
                    if filters.get("price_max"):
                        queryset = queryset.filter(price__lte=filters["price_max"])
                    if filters.get("location"):
                        value = filters["location"]
                        queryset = queryset.filter(
                            Q(city__icontains=value)
                            | Q(district__icontains=value)
                            | Q(neighbourhood__icontains=value)
                        )
                    matches = list(queryset[:10])
                    SavedSearch.objects.filter(pk=saved.pk).update(
                        last_checked_at=checked_at,
                        last_match_count=len(matches),
                        last_check_error="",
                    )
                    if not matches:
                        continue
                    links = "\n".join(
                        f"- {item.title}: {getattr(settings, 'STOREFRONT_PUBLIC_URL', 'http://localhost:3000')}/agency/{saved.agency.slug}/properties/{item.share_slug}"
                        for item in matches
                    )
                    send_mail(
                        f"New matches for {saved.name}",
                        f"Hi {saved.customer.full_name},\n\nNew properties match your saved search:\n{links}",
                        settings.DEFAULT_FROM_EMAIL,
                        [saved.customer.email],
                        fail_silently=False,
                    )
                    SavedSearch.objects.filter(pk=saved.pk).update(
                        last_notified_at=timezone.now(),
                        last_check_error="",
                    )
                    sent += 1
                except Exception as exc:
                    failed += 1
                    SavedSearch.objects.filter(pk=saved.pk).update(
                        last_checked_at=checked_at,
                        last_check_error=str(exc)[:2000],
                    )
            job.result = {"checked": checked, "sent": sent, "failed": failed}
        self.stdout.write(self.style.SUCCESS(f"Sent {sent} saved-search alerts."))
