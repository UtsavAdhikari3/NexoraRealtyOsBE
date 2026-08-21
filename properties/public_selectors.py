from django.db.models import QuerySet
from django.utils import timezone

from agencies.models import Agency
from agencies.public_selectors import public_agencies

from .models import Property


PUBLIC_PROPERTY_STATUSES = (
    "available",
    "reserved",
    "under_negotiation",
)


def public_properties(
    *,
    agency: Agency | None = None,
    queryset: QuerySet[Property] | None = None,
) -> QuerySet[Property]:
    """Apply the authoritative public website visibility policy to properties."""
    now = timezone.now()
    queryset = queryset if queryset is not None else Property.objects.all()
    queryset = queryset.filter(
        agency__in=public_agencies(),
        is_published=True,
        status__in=PUBLIC_PROPERTY_STATUSES,
        requires_republish_approval=False,
        availability_verified_at__isnull=False,
        listing_expires_at__gt=now,
    )
    if agency is not None:
        queryset = queryset.filter(agency=agency)
    return queryset
