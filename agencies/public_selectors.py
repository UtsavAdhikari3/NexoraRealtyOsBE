from django.db.models import Q, QuerySet
from django.shortcuts import get_object_or_404
from django.utils import timezone

from .models import Agency


def public_agencies() -> QuerySet[Agency]:
    """Return agencies whose published websites may be served publicly."""
    now = timezone.now()
    return Agency.objects.filter(
        payment_status=Agency.PAYMENT_PAID,
        is_active=True,
        is_website_published=True,
    ).filter(
        Q(subscription_expires_at__isnull=True)
        | Q(subscription_expires_at__gt=now)
    )


def get_public_agency(**lookup) -> Agency:
    return get_object_or_404(public_agencies(), **lookup)
