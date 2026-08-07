import re
from datetime import timedelta
from decimal import Decimal

from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from .models import Property, PropertyDuplicateFlag, PropertyHistory, PropertyListingReminder


def record_property_history(property_obj, event_type, summary, actor=None, changes=None, note=""):
    return PropertyHistory.objects.create(
        agency=property_obj.agency,
        property=property_obj,
        actor=actor,
        event_type=event_type,
        summary=summary,
        changes=changes or {},
        note=note,
    )


def _normalized(value):
    return re.sub(r"[^a-z0-9]+", " ", (value or "").lower()).strip()


def detect_duplicate_listings(property_obj):
    candidates = Property.objects.filter(agency=property_obj.agency).exclude(pk=property_obj.pk)
    if property_obj.district:
        candidates = candidates.filter(district__iexact=property_obj.district)
    detected = []
    for candidate in candidates[:250]:
        score, reasons = 0, []
        address = _normalized(property_obj.address)
        if address and address == _normalized(candidate.address):
            score += 50; reasons.append("Same normalized address")
        title = _normalized(property_obj.title)
        if title and title == _normalized(candidate.title):
            score += 25; reasons.append("Same title")
        if property_obj.latitude is not None and candidate.latitude is not None:
            lat_gap = abs(Decimal(property_obj.latitude) - Decimal(candidate.latitude))
            lng_gap = abs(Decimal(property_obj.longitude) - Decimal(candidate.longitude)) if property_obj.longitude is not None and candidate.longitude is not None else Decimal("1")
            if lat_gap <= Decimal("0.0005") and lng_gap <= Decimal("0.0005"):
                score += 40; reasons.append("Nearly identical map location")
        if property_obj.land_area_sqft and candidate.land_area_sqft:
            difference = abs(property_obj.land_area_sqft - candidate.land_area_sqft)
            if difference / max(property_obj.land_area_sqft, candidate.land_area_sqft) <= Decimal("0.02"):
                score += 25; reasons.append("Land area within 2%")
        if score >= 50:
            flag, created = PropertyDuplicateFlag.objects.update_or_create(
                property=property_obj, candidate=candidate,
                defaults={"agency": property_obj.agency, "score": min(score, 100), "reasons": reasons},
            )
            detected.append(flag)
            if created:
                record_property_history(
                    property_obj, "duplicate_flagged",
                    f"Possible duplicate of {candidate.title}",
                    changes={"candidate_id": candidate.id, "score": min(score, 100), "reasons": reasons},
                )
    return detected


@transaction.atomic
def confirm_listing_freshness(property_obj, actor, valid_for_days=30, owner_confirmed=False):
    now = timezone.now()
    property_obj.availability_verified_at = now
    property_obj.listing_expires_at = now + timedelta(days=valid_for_days)
    if owner_confirmed:
        property_obj.owner_confirmed_at = now
    if not property_obj.requires_republish_approval:
        property_obj.is_published = property_obj.status in {"available", "reserved", "under_negotiation"}
    property_obj.save(update_fields=[
        "availability_verified_at", "listing_expires_at", "owner_confirmed_at",
        "is_published", "updated_at",
    ])
    record_property_history(
        property_obj, "freshness_confirmed", f"Listing confirmed for {valid_for_days} days",
        actor=actor, changes={"listing_expires_at": property_obj.listing_expires_at.isoformat(), "owner_confirmed": owner_confirmed},
    )
    return property_obj


def process_listing_freshness(now=None):
    from agencies.localization import format_localized_date, render_message
    from operations.models import Notification
    from users.models import AgencyUser

    now = now or timezone.now()
    active = Property.objects.filter(
        is_published=True, listing_expires_at__isnull=False,
    ).select_related("assigned_agent", "agency")
    reminder_windows = [
        ("seven_days", timedelta(days=7)), ("three_days", timedelta(days=3)),
        ("one_day", timedelta(days=1)),
    ]
    notifications_created = 0
    for property_obj in active:
        remaining = property_obj.listing_expires_at - now
        reminder_type = None
        if remaining.total_seconds() <= 0:
            reminder_type = "expired"
        else:
            for candidate_type, window in reversed(reminder_windows):
                if remaining <= window:
                    reminder_type = candidate_type
                    break
        if not reminder_type:
            continue
        reminder, created = PropertyListingReminder.objects.get_or_create(
            property=property_obj, expiry_at=property_obj.listing_expires_at,
            reminder_type=reminder_type,
        )
        if created:
            template_key = "listing_expired" if reminder_type == "expired" else "listing_confirmation_due"
            localized = render_message(
                property_obj.agency, template_key,
                property_title=property_obj.title,
                expiry_date=format_localized_date(
                    property_obj.listing_expires_at,
                    date_system=property_obj.agency.default_date_system,
                    language=property_obj.agency.default_language,
                    nepali_digits=property_obj.agency.use_nepali_digits,
                    include_time=True,
                ),
            )
            recipients = AgencyUser.objects.filter(
                agency=property_obj.agency, is_active=True,
            ).filter(Q(id=property_obj.assigned_agent_id) | Q(role__in=["agency_owner", "agency_manager"])).distinct()
            Notification.objects.bulk_create([
                Notification(
                    agency=property_obj.agency, user=user,
                    title=localized["subject"],
                    message=localized["body"],
                    category="listing_freshness", link=f"/properties/{property_obj.id}",
                ) for user in recipients
            ])
            notifications_created += recipients.count()
        if reminder_type == "expired":
            property_obj.is_published = False
            property_obj.requires_republish_approval = True
            property_obj.republish_approval_status = "not_required"
            property_obj.save(update_fields=[
                "is_published", "requires_republish_approval", "republish_approval_status", "updated_at",
            ])
            if created:
                record_property_history(property_obj, "expired", "Listing automatically hidden after expiry")
    return notifications_created
