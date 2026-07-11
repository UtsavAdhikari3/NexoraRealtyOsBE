from django.db.models import Count, Q
from django.utils import timezone
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from leads.models import Lead
from properties.models import Property, PropertyEvent
from site_visits.models import SiteVisit
from users.models import AgencyUser
from leads.serializers import LeadSerializer


class DashboardSummaryView(APIView):
    permission_classes = [IsAuthenticated]
    serializer_class = LeadSerializer

    def get(self, request):
        user = request.user
        if not user.agency_id:
            return Response({"detail": "An agency account is required."}, status=403)

        now = timezone.now()
        leads = Lead.objects.filter(agency=user.agency)
        visits = SiteVisit.objects.filter(agency=user.agency)

        if user.role == AgencyUser.ROLE_AGENT:
            leads = leads.filter(assigned_agent=user)
            visits = visits.filter(assigned_agent=user)

        lead_statuses = {
            item["status"]: item["count"]
            for item in leads.values("status").annotate(count=Count("id"))
        }
        lead_sources = {
            item["source"]: item["count"]
            for item in leads.values("source").annotate(count=Count("id"))
        }

        properties = Property.objects.filter(agency=user.agency)
        events = PropertyEvent.objects.filter(agency=user.agency)

        return Response(
            {
                "totals": {
                    "properties": properties.count(),
                    "published_properties": properties.filter(is_published=True).count(),
                    "leads": leads.count(),
                    "new_leads": leads.filter(status="new").count(),
                    "agents": AgencyUser.objects.filter(
                        agency=user.agency,
                        role=AgencyUser.ROLE_AGENT,
                        is_active=True,
                    ).count(),
                    "property_views": events.filter(event_type=PropertyEvent.EVENT_VIEW).count(),
                    "inquiries": events.filter(event_type=PropertyEvent.EVENT_INQUIRY).count(),
                },
                "follow_ups": {
                    "overdue": leads.filter(
                        follow_up_status=Lead.FOLLOW_UP_PENDING,
                        next_follow_up_at__date__lt=now.date(),
                    ).count(),
                    "due_today": leads.filter(
                        follow_up_status=Lead.FOLLOW_UP_PENDING,
                        next_follow_up_at__date=now.date(),
                    ).count(),
                    "upcoming": leads.filter(
                        follow_up_status=Lead.FOLLOW_UP_PENDING,
                        next_follow_up_at__date__gt=now.date(),
                    ).count(),
                },
                "site_visits": {
                    "today": visits.filter(scheduled_at__date=now.date()).count(),
                    "upcoming": visits.filter(
                        scheduled_at__gt=now,
                        status__in=["requested", "scheduled", "rescheduled"],
                    ).count(),
                },
                "leads_by_status": lead_statuses,
                "leads_by_source": lead_sources,
                "top_properties": list(
                    properties.annotate(
                        inquiry_count=Count(
                            "events",
                            filter=Q(events__event_type=PropertyEvent.EVENT_INQUIRY),
                            distinct=True,
                        ),
                        view_count=Count(
                            "events",
                            filter=Q(events__event_type=PropertyEvent.EVENT_VIEW),
                            distinct=True,
                        ),
                    )
                    .values("id", "title", "view_count", "inquiry_count")
                    .order_by("-inquiry_count", "-view_count")[:5]
                ),
            }
        )
