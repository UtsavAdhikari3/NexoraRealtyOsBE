from django.conf import settings
from django.core.mail import send_mail
from django.core.management.base import BaseCommand
from django.db.models import Q
from django.utils import timezone

from operations.models import SavedSearch
from properties.models import Property


class Command(BaseCommand):
    help = "Email customers when new public properties match their saved searches."

    def handle(self, *args, **options):
        sent = 0
        for saved in SavedSearch.objects.filter(alerts_enabled=True).select_related("agency", "customer"):
            queryset = Property.objects.filter(
                agency=saved.agency,
                status="available",
                is_published=True,
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
                queryset = queryset.filter(Q(city__icontains=value) | Q(district__icontains=value) | Q(neighbourhood__icontains=value))
            matches = list(queryset[:10])
            if not matches:
                continue
            links = "\n".join(
                f"- {item.title}: {getattr(settings, 'PUBLIC_FRONTEND_URL', 'http://localhost:5173')}/agency/{saved.agency.slug}/properties/{item.id}"
                for item in matches
            )
            send_mail(
                f"New matches for {saved.name}",
                f"Hi {saved.customer.full_name},\n\nNew properties match your saved search:\n{links}",
                settings.DEFAULT_FROM_EMAIL,
                [saved.customer.email],
                fail_silently=False,
            )
            saved.last_notified_at = timezone.now()
            saved.save(update_fields=["last_notified_at", "updated_at"])
            sent += 1
        self.stdout.write(self.style.SUCCESS(f"Sent {sent} saved-search alerts."))
