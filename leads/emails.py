from django.conf import settings
from django.core.mail import send_mail
from django.db import transaction
from django.utils import timezone

from operations.models import Notification
from agencies.localization import (
    format_localized_date, format_nepal_phone, render_message,
)
from .models import Lead, LeadAutomationEvent


@transaction.atomic
def send_follow_up_reminder(lead_id):
    lead = Lead.objects.select_for_update().get(id=lead_id)

    if lead.follow_up_reminder_sent_at or not lead.next_follow_up_at:
        return False

    if not lead.assigned_agent:
        Lead.objects.filter(id=lead.id).update(
            follow_up_reminder_error="No assigned agent is available."
        )
        return False

    now = timezone.now()
    agency = lead.agency
    property_interest = lead.property_interests.select_related("property").first()
    property_title = property_interest.property.title if property_interest else "-"
    due = format_localized_date(
        lead.next_follow_up_at,
        date_system=agency.default_date_system,
        language=agency.default_language,
        nepali_digits=agency.use_nepali_digits,
        include_time=True,
    )
    localized = render_message(
        agency, "lead_follow_up", lead_name=lead.full_name,
        follow_up_date=due, property_title=property_title,
    )
    Notification.objects.create(
        agency=lead.agency,
        user=lead.assigned_agent,
        title=localized["subject"],
        message=localized["body"],
        category="lead_automation",
        link=f"/inbox?lead={lead.id}",
    )
    error = ""
    try:
        if lead.assigned_agent.email:
            send_mail(
                subject=localized["subject"],
                message=(
                    f"{localized['body']}\n\n"
                    f"{lead.full_name}\n{format_nepal_phone(lead.phone)}\n"
                    f"{lead.notes or '-'}"
                ),
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[lead.assigned_agent.email],
                fail_silently=False,
            )
        else:
            error = "In-app reminder sent; assigned agent has no email."
    except Exception as exc:
        error = f"In-app reminder sent; email failed: {exc}"
    Lead.objects.filter(id=lead.id).update(
        follow_up_reminder_sent_at=now,
        follow_up_reminder_error=error,
    )
    LeadAutomationEvent.objects.create(
        agency=lead.agency,
        lead=lead,
        event_type="follow_up_reminder",
        to_agent=lead.assigned_agent,
        summary="Follow-up reminder sent",
        details={"due_at": lead.next_follow_up_at.isoformat(), "email_error": error},
    )
    return True
