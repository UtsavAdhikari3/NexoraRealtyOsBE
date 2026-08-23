from django.db.models import Q
from agencies.phone import nepal_phone_national_digits, normalize_nepal_phone

from .models import Lead, LeadStatusHistory


def normalize_phone(value):
    """Normalize supported Nepal phone numbers to the +977 storage format."""
    return normalize_nepal_phone(value)


def get_or_create_public_lead(
    *,
    agency,
    full_name,
    phone,
    email="",
    assigned_agent=None,
    preferred_location="",
    purpose="",
    property_type="",
    notes="",
    property_obj=None,
):
    normalized_phone = normalize_phone(phone)
    national_phone = nepal_phone_national_digits(phone)
    normalized_email = (email or "").lower().strip()

    identity_filter = Q(phone__in={normalized_phone, national_phone})
    if normalized_email:
        identity_filter |= Q(email__iexact=normalized_email)

    lead = (
        Lead.objects.filter(agency=agency)
        .filter(identity_filter)
        .exclude(status__in=["lost", "archived"])
        .order_by("-updated_at")
        .first()
    )

    if lead:
        changed_fields = []

        if lead.phone != normalized_phone:
            lead.phone = normalized_phone
            changed_fields.append("phone")

        if assigned_agent and lead.assigned_agent_id is None:
            lead.assigned_agent = assigned_agent
            changed_fields.append("assigned_agent")

        if normalized_email and not lead.email:
            lead.email = normalized_email
            changed_fields.append("email")

        if preferred_location and not lead.preferred_location:
            lead.preferred_location = preferred_location
            changed_fields.append("preferred_location")

        if purpose and not lead.purpose:
            lead.purpose = purpose
            changed_fields.append("purpose")

        if property_type and not lead.property_type:
            lead.property_type = property_type
            changed_fields.append("property_type")

        if notes and not lead.notes:
            lead.notes = notes
            changed_fields.append("notes")

        if changed_fields:
            changed_fields.append("updated_at")
            lead.save(update_fields=changed_fields)

        if not lead.assigned_agent_id or not lead.assigned_at:
            from .automation import apply_lead_automation
            apply_lead_automation(lead, property_obj=property_obj)
            lead.refresh_from_db()

        return lead, False

    lead = Lead.objects.create(
        agency=agency,
        assigned_agent=assigned_agent,
        full_name=full_name.strip(),
        phone=normalized_phone,
        email=normalized_email,
        source="website",
        status="new",
        preferred_location=preferred_location,
        purpose=purpose,
        property_type=property_type,
        notes=notes,
    )
    LeadStatusHistory.objects.create(
        agency=agency,
        lead=lead,
        to_status=lead.status,
    )
    from .automation import apply_lead_automation
    apply_lead_automation(lead, property_obj=property_obj)
    lead.refresh_from_db()
    return lead, True
