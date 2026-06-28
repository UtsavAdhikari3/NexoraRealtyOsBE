from django.conf import settings
from django.core.mail import send_mail
from django.utils import timezone

from .models import SiteVisit


def format_property_location(property_obj):
    parts = [
        property_obj.neighbourhood,
        property_obj.city,
        property_obj.district,
        property_obj.province,
    ]

    return ", ".join(
        [
            part
            for part in parts
            if part
        ]
    )


def send_site_visit_scheduled_email(site_visit_id):
    site_visit = SiteVisit.objects.select_related(
        "lead",
        "property",
        "assigned_agent",
        "agency",
    ).get(id=site_visit_id)

    if site_visit.scheduled_email_sent_at:
        return False

    lead = site_visit.lead

    if not lead.email:
        return False

    property_obj = site_visit.property
    assigned_agent = site_visit.assigned_agent

    property_location = format_property_location(property_obj)

    agent_name = assigned_agent.full_name if assigned_agent else "our agent"
    agent_email = assigned_agent.email if assigned_agent else ""

    subject = "Your site visit has been scheduled"

    message = f"""Hi {lead.full_name},

Your site visit has been scheduled.

Property: {property_obj.title}
Location: {property_location}
Date/Time: {site_visit.scheduled_at}

Assigned Agent: {agent_name}
Agent Email: {agent_email}

Notes:
{site_visit.notes or "No additional notes."}

Thank you,
Nexora RealtyOS
"""

    try:
        send_mail(
            subject=subject,
            message=message,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[lead.email],
            fail_silently=False,
        )

        SiteVisit.objects.filter(
            id=site_visit.id
        ).update(
            scheduled_email_sent_at=timezone.now(),
            scheduled_email_error="",
        )

        return True

    except Exception as e:
        SiteVisit.objects.filter(
            id=site_visit.id
        ).update(
            scheduled_email_error=str(e),
        )

        return False