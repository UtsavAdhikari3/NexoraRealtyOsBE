import logging
import re
from datetime import timedelta

from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from operations.models import Notification
from users.models import AgencyUser
from .models import (
    Lead, LeadAssignmentRule, LeadAutomationEvent, LeadAutomationSettings,
    LeadDuplicateFlag,
)


ACTIVE_STATUSES = {
    "new", "contacted", "interested", "site_visit_scheduled",
    "site_visit_completed", "negotiating", "token_booking", "follow_up_later",
}

logger = logging.getLogger(__name__)


def _active_statuses(agency):
    """Return built-in and agency-defined open lead stages."""
    from operations.models import PipelineStage

    custom = PipelineStage.objects.filter(
        agency=agency, module="lead", is_closed=False,
    ).values_list("key", flat=True)
    return ACTIVE_STATUSES | set(custom)


def get_automation_settings(agency):
    settings, _ = LeadAutomationSettings.objects.get_or_create(agency=agency)
    return settings


def _managers(agency):
    return AgencyUser.objects.filter(
        agency=agency,
        is_active=True,
        role__in=[AgencyUser.ROLE_AGENCY_OWNER, AgencyUser.ROLE_AGENCY_MANAGER],
    )


def _notify(users, *, agency, title, message, lead):
    Notification.objects.bulk_create([
        Notification(
            agency=agency,
            user=user,
            title=title,
            message=message,
            category="lead_automation",
            link=f"/inbox?lead={lead.id}",
        )
        for user in users
    ])


def _active_count(agent, exclude_lead=None):
    queryset = Lead.objects.filter(
        assigned_agent=agent,
        status__in=_active_statuses(agent.agency),
    )
    if exclude_lead:
        queryset = queryset.exclude(pk=exclude_lead.pk)
    return queryset.count()


def _agent_is_eligible(agent, settings, exclude_lead=None):
    if not agent or not agent.is_active or agent.role != AgencyUser.ROLE_AGENT:
        return False
    if agent.agency_id != settings.agency_id:
        return False
    limit = settings.max_active_leads_per_agent
    return not limit or _active_count(agent, exclude_lead) < limit


def _round_robin_agent(settings, *, exclude_agent=None, lead=None):
    agents = list(AgencyUser.objects.filter(
        agency=settings.agency,
        role=AgencyUser.ROLE_AGENT,
        is_active=True,
    ).order_by("id"))
    agents = [
        agent for agent in agents
        if agent != exclude_agent and _agent_is_eligible(agent, settings, lead)
    ]
    if not agents:
        return None
    last_id = settings.round_robin_last_agent_id or 0
    selected = next((agent for agent in agents if agent.id > last_id), agents[0])
    settings.round_robin_last_agent = selected
    settings.save(update_fields=["round_robin_last_agent", "updated_at"])
    return selected


def _lead_property(lead, property_obj=None):
    if property_obj:
        return property_obj
    interest = lead.property_interests.select_related("property").first()
    return interest.property if interest else None


def _rule_matches(rule, lead, property_obj):
    if rule.match_property_id and (
        not property_obj or property_obj.id != rule.match_property_id
    ):
        return False
    property_type = property_obj.property_type if property_obj else lead.property_type
    if rule.match_property_type and property_type != rule.match_property_type:
        return False
    if rule.match_location:
        location = " ".join(filter(None, [
            lead.preferred_location,
            getattr(property_obj, "tole", ""),
            getattr(property_obj, "municipality", ""),
            getattr(property_obj, "city", ""),
            getattr(property_obj, "district", ""), getattr(property_obj, "province", ""),
        ])).lower()
        if rule.match_location.lower() not in location:
            return False
    return True


def _agent_for_method(method, settings, property_obj, rule=None, lead=None, exclude_agent=None):
    if method == "specific_agent":
        agent = rule.assign_to_agent if rule else None
        return agent if _agent_is_eligible(agent, settings, lead) else None
    if method == "listing_agent":
        agent = getattr(property_obj, "assigned_agent", None)
        return agent if _agent_is_eligible(agent, settings, lead) else None
    if method == "round_robin":
        return _round_robin_agent(
            settings, exclude_agent=exclude_agent, lead=lead
        )
    return None


def stamp_assignment(
    lead, agent, settings=None, *, rule=None, reassignment=False, previous_agent=None
):
    settings = settings or get_automation_settings(lead.agency)
    now = timezone.now()
    previous = previous_agent if previous_agent is not None else lead.assigned_agent
    lead.assigned_agent = agent
    lead.assigned_at = now
    lead.response_due_at = now + timedelta(minutes=settings.response_sla_minutes)
    lead.assignment_responded_at = None
    lead.escalated_at = None
    lead.neglect_alerted_at = None
    lead.last_agent_activity_at = now
    update_fields = [
        "assigned_agent", "assigned_at", "response_due_at",
        "assignment_responded_at", "escalated_at", "neglect_alerted_at",
        "last_agent_activity_at", "updated_at",
    ]
    event_type = "assigned"
    summary = f"Lead assigned to {agent.full_name}"
    if reassignment:
        lead.reassigned_at = now
        lead.reassignment_count += 1
        update_fields.extend(["reassigned_at", "reassignment_count"])
        event_type = "reassigned"
        summary = f"Inactive lead reassigned to {agent.full_name}"
    lead.save(update_fields=update_fields)
    LeadAutomationEvent.objects.create(
        agency=lead.agency,
        lead=lead,
        rule=rule,
        event_type=event_type,
        from_agent=previous,
        to_agent=agent,
        summary=summary,
        details={"response_due_at": lead.response_due_at.isoformat()},
    )
    _notify(
        [agent], agency=lead.agency,
        title="Lead reassigned" if reassignment else "New lead assigned",
        message=f"{lead.full_name} - respond by {lead.response_due_at:%Y-%m-%d %H:%M}",
        lead=lead,
    )
    return lead


@transaction.atomic
def apply_lead_automation(lead, property_obj=None, force=False):
    lead = Lead.objects.select_for_update().select_related("agency").get(pk=lead.pk)
    settings = get_automation_settings(lead.agency)
    settings = LeadAutomationSettings.objects.select_for_update().get(pk=settings.pk)
    if not settings.is_enabled:
        return lead
    property_obj = _lead_property(lead, property_obj)
    if settings.auto_detect_duplicates:
        detect_duplicate_leads(lead)
    if lead.assigned_agent_id and not force:
        if not lead.assigned_at:
            stamp_assignment(lead, lead.assigned_agent, settings)
        return lead

    matched_rule = None
    agent = None
    for rule in LeadAssignmentRule.objects.filter(
        agency=lead.agency, is_active=True
    ).select_related("assign_to_agent", "match_property").order_by("priority", "id"):
        if not _rule_matches(rule, lead, property_obj):
            continue
        matched_rule = rule
        agent = _agent_for_method(
            rule.assignment_method, settings, property_obj, rule=rule, lead=lead
        )
        # The highest-priority matching rule owns the decision. If it cannot
        # assign, use the configured fallback rather than a lower-priority rule.
        break

    if not agent and settings.fallback_assignment != "unassigned":
        matched_rule = None
        agent = _agent_for_method(
            settings.fallback_assignment, settings, property_obj, lead=lead
        )
        if not agent and settings.fallback_assignment == "listing_agent":
            agent = _round_robin_agent(settings, lead=lead)
    if agent:
        stamp_assignment(lead, agent, settings, rule=matched_rule)
    return lead


def record_agent_response(lead, agent, occurred_at=None):
    if (
        not agent
        or agent.role != AgencyUser.ROLE_AGENT
        or lead.assigned_agent_id != agent.id
    ):
        return
    occurred_at = occurred_at or timezone.now()
    update_fields = ["assignment_responded_at", "last_agent_activity_at", "updated_at"]
    lead.assignment_responded_at = occurred_at
    lead.last_agent_activity_at = occurred_at
    first_response = lead.first_responded_at is None
    if first_response:
        lead.first_responded_at = occurred_at
        baseline = lead.assigned_at or lead.created_at
        lead.response_time_seconds = max(0, int((occurred_at - baseline).total_seconds()))
        update_fields.extend(["first_responded_at", "response_time_seconds"])
    lead.save(update_fields=update_fields)
    if first_response:
        LeadAutomationEvent.objects.create(
            agency=lead.agency,
            lead=lead,
            event_type="response",
            to_agent=agent,
            summary=f"First response recorded from {agent.full_name}",
            details={"response_time_seconds": lead.response_time_seconds},
        )


def _normalized(value):
    return re.sub(r"[^a-z0-9]+", "", (value or "").lower())


def _normalized_phone(value):
    phone = re.sub(r"\D+", "", value or "")
    if phone.startswith("977") and len(phone) == 13:
        phone = phone[3:]
    return phone


def detect_duplicate_leads(lead):
    candidates = Lead.objects.filter(agency=lead.agency).exclude(pk=lead.pk).exclude(
        status="archived"
    ).order_by("id")[:500]
    detected = []
    phone = _normalized_phone(lead.phone)
    email = (lead.email or "").lower().strip()
    name = _normalized(lead.full_name)
    for candidate in candidates:
        score, reasons = 0, []
        candidate_phone = _normalized_phone(candidate.phone)
        if phone and phone == candidate_phone:
            score += 100
            reasons.append("Same phone number")
        elif len(phone) >= 7 and phone[-7:] == candidate_phone[-7:]:
            score += 70
            reasons.append("Matching phone suffix")
        if email and email == (candidate.email or "").lower().strip():
            score += 80
            reasons.append("Same email address")
        if name and name == _normalized(candidate.full_name):
            score += 25
            reasons.append("Same name")
        if score < 70:
            continue
        flag, created = LeadDuplicateFlag.objects.update_or_create(
            lead=lead,
            candidate=candidate,
            defaults={
                "agency": lead.agency,
                "score": min(score, 100),
                "reasons": reasons,
            },
        )
        detected.append(flag)
        if created:
            LeadAutomationEvent.objects.create(
                agency=lead.agency,
                lead=lead,
                event_type="duplicate",
                summary=f"Possible duplicate of {candidate.full_name}",
                details={"candidate_id": candidate.id, "score": flag.score},
            )
            _notify(
                _managers(lead.agency), agency=lead.agency,
                title="Possible duplicate lead",
                message=f"{lead.full_name} may duplicate {candidate.full_name}",
                lead=lead,
            )
    return detected


@transaction.atomic
def _process_one_lead(lead_id, now):
    """Process one lead under row locks so concurrent schedulers are harmless."""
    lead = Lead.objects.select_for_update().select_related("agency").get(pk=lead_id)
    settings = LeadAutomationSettings.objects.select_for_update().filter(
        agency=lead.agency
    ).first()
    if not settings:
        settings = get_automation_settings(lead.agency)
        settings = LeadAutomationSettings.objects.select_for_update().get(pk=settings.pk)

    counts = {"escalated": 0, "alerts": 0, "reassigned": 0}
    if (
        not settings.is_enabled
        or not lead.assigned_agent_id
        or lead.status not in _active_statuses(lead.agency)
    ):
        return counts

    assigned_at = lead.assigned_at or lead.created_at
    activity_at = lead.last_agent_activity_at or assigned_at
    inactive_assignee = not lead.assigned_agent.is_active

    escalation_at = assigned_at + timedelta(minutes=settings.escalation_minutes)
    if not lead.assignment_responded_at and not lead.escalated_at and now >= escalation_at:
        lead.escalated_at = now
        lead.save(update_fields=["escalated_at", "updated_at"])
        users = list(_managers(lead.agency)) + [lead.assigned_agent]
        _notify(
            users, agency=lead.agency, title="Lead response SLA missed",
            message=f"{lead.assigned_agent.full_name} has not responded to {lead.full_name}",
            lead=lead,
        )
        LeadAutomationEvent.objects.create(
            agency=lead.agency, lead=lead, event_type="escalated",
            from_agent=lead.assigned_agent,
            summary="Lead escalated after missed response SLA",
        )
        counts["escalated"] += 1

    alert_at = activity_at + timedelta(hours=settings.manager_alert_hours)
    if not lead.neglect_alerted_at and now >= alert_at:
        lead.neglect_alerted_at = now
        lead.save(update_fields=["neglect_alerted_at", "updated_at"])
        _notify(
            _managers(lead.agency), agency=lead.agency,
            title="Neglected lead alert",
            message=f"No recent agent activity for {lead.full_name}", lead=lead,
        )
        LeadAutomationEvent.objects.create(
            agency=lead.agency, lead=lead, event_type="neglect_alert",
            from_agent=lead.assigned_agent,
            summary="Manager alerted about neglected lead",
        )
        counts["alerts"] += 1

    reassign_at = activity_at + timedelta(hours=settings.inactive_reassign_hours)
    if settings.auto_reassign_inactive and (inactive_assignee or now >= reassign_at):
        replacement = _round_robin_agent(
            settings, exclude_agent=lead.assigned_agent, lead=lead
        )
        if replacement:
            stamp_assignment(lead, replacement, settings, reassignment=True)
            counts["reassigned"] += 1
    return counts


def process_lead_automation(now=None, agency=None):
    now = now or timezone.now()
    counts = {"escalated": 0, "alerts": 0, "reassigned": 0}
    leads = Lead.objects.filter(
        assigned_agent__isnull=False,
        agency__is_active=True,
    ).exclude(status__in=["won", "lost", "archived"])
    if agency is not None:
        leads = leads.filter(agency=agency)
    for lead_id in leads.order_by("id").values_list("id", flat=True).iterator():
        try:
            result = _process_one_lead(lead_id, now)
        except Exception:
            logger.exception("Lead automation failed for lead %s", lead_id)
            continue
        for key in counts:
            counts[key] += result[key]
    return counts
