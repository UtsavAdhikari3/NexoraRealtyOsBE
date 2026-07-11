from django.conf import settings
from django.core.mail import send_mail
from django.utils import timezone

from .models import Lead


def send_follow_up_reminder(lead_id):
    lead = Lead.objects.select_related("assigned_agent", "agency").get(id=lead_id)

    if lead.follow_up_reminder_sent_at or not lead.next_follow_up_at:
        return False

    if not lead.assigned_agent or not lead.assigned_agent.email:
        Lead.objects.filter(id=lead.id).update(
            follow_up_reminder_error="No assigned agent email is available."
        )
        return False

    try:
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
        Lead.objects.filter(id=lead.id).update(
            follow_up_reminder_sent_at=timezone.now(),
            follow_up_reminder_error="",
        )
        return True
    except Exception as exc:
        Lead.objects.filter(id=lead.id).update(
            follow_up_reminder_error=str(exc)
        )
        return False
