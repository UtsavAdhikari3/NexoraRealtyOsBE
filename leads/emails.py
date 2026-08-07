from django.conf import settings
from django.core.mail import send_mail
from django.db import transaction
from django.utils import timezone

from operations.models import Notification
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
    Notification.objects.create(
        agency=lead.agency,
        user=lead.assigned_agent,
        title=f"Follow-up due: {lead.full_name}",
        message=f"Follow up by {lead.next_follow_up_at:%Y-%m-%d %H:%M}.",
        category="lead_automation",
        link=f"/inbox?lead={lead.id}",
    )
    error = ""
    try:
        if lead.assigned_agent.email:
            send_mail(
                subject=f"Follow-up due: {lead.full_name}",
                message=(
                    f"A lead follow-up is due.\n\n"
                    f"Lead: {lead.full_name}\nPhone: {lead.phone}\n"
                    f"Due: {lead.next_follow_up_at}\n"
                    f"Notes: {lead.notes or 'No notes.'}"
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
