from django.db.models import Q

from rest_framework import generics
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.exceptions import PermissionDenied

from drf_spectacular.utils import (
    extend_schema,
    extend_schema_view,
    OpenApiParameter,
)
from drf_spectacular.types import OpenApiTypes
from django.db import transaction
from .models import SiteVisit
from .serializers import SiteVisitSerializer, PublicSiteVisitRequestSerializer

from django.db import transaction
from django.shortcuts import get_object_or_404
from .emails import send_site_visit_scheduled_email

from rest_framework import status
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, AllowAny

from properties.models import Property
from leads.models import Lead, LeadPropertyInterest, LeadInteraction


SITE_VISIT_FILTER_PARAMETERS = [
    OpenApiParameter(
        name="status",
        type=OpenApiTypes.STR,
        location=OpenApiParameter.QUERY,
        required=False,
        description="Filter by status. Example: scheduled, completed, cancelled, no_show, rescheduled"
    ),
    OpenApiParameter(
        name="assigned_agent",
        type=OpenApiTypes.STR,
        location=OpenApiParameter.QUERY,
        required=False,
        description="Filter by assigned agent ID, or use 'unassigned'"
    ),
    OpenApiParameter(
        name="lead",
        type=OpenApiTypes.INT,
        location=OpenApiParameter.QUERY,
        required=False,
        description="Filter by lead ID"
    ),
    OpenApiParameter(
        name="property",
        type=OpenApiTypes.INT,
        location=OpenApiParameter.QUERY,
        required=False,
        description="Filter by property ID"
    ),
    OpenApiParameter(
        name="date_from",
        type=OpenApiTypes.DATE,
        location=OpenApiParameter.QUERY,
        required=False,
        description="Filter site visits scheduled on or after this date. Format: YYYY-MM-DD"
    ),
    OpenApiParameter(
        name="date_to",
        type=OpenApiTypes.DATE,
        location=OpenApiParameter.QUERY,
        required=False,
        description="Filter site visits scheduled on or before this date. Format: YYYY-MM-DD"
    ),
    OpenApiParameter(
        name="search",
        type=OpenApiTypes.STR,
        location=OpenApiParameter.QUERY,
        required=False,
        description="Search lead name, phone, property title, or notes"
    ),
]


def queue_site_visit_scheduled_email(site_visit):
    if site_visit.status != "scheduled":
        return

    if site_visit.scheduled_email_sent_at:
        return

    transaction.on_commit(
        lambda: send_site_visit_scheduled_email(site_visit.id)
    )

def user_can_manage_all_site_visits(user):
    return user.role in [
        "agency_owner",
        "agency_manager",
    ]


def get_accessible_site_visits_for_user(user):
    queryset = SiteVisit.objects.filter(
        agency=user.agency
    )

    if user.role == "agent":
        queryset = queryset.filter(
            assigned_agent=user
        )

    return queryset


@extend_schema_view(
    get=extend_schema(parameters=SITE_VISIT_FILTER_PARAMETERS)
)
class SiteVisitListCreateView(generics.ListCreateAPIView):
    serializer_class = SiteVisitSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        queryset = get_accessible_site_visits_for_user(
            self.request.user
        ).select_related(
            "agency",
            "lead",
            "property",
            "assigned_agent",
            "created_by",
        ).order_by("-scheduled_at")

        status_value = self.request.query_params.get("status")
        assigned_agent = self.request.query_params.get("assigned_agent")
        lead = self.request.query_params.get("lead")
        property_id = self.request.query_params.get("property")
        date_from = self.request.query_params.get("date_from")
        date_to = self.request.query_params.get("date_to")
        search = self.request.query_params.get("search")

        if status_value and status_value != "all":
            queryset = queryset.filter(status=status_value)

        if assigned_agent and assigned_agent != "all":
            if assigned_agent == "unassigned":
                queryset = queryset.filter(assigned_agent__isnull=True)
            elif assigned_agent.isdigit():
                queryset = queryset.filter(assigned_agent_id=int(assigned_agent))
            else:
                queryset = queryset.none()

        if lead and str(lead).isdigit():
            queryset = queryset.filter(lead_id=int(lead))

        if property_id and str(property_id).isdigit():
            queryset = queryset.filter(property_id=int(property_id))

        if date_from:
            queryset = queryset.filter(
                scheduled_at__date__gte=date_from
            )

        if date_to:
            queryset = queryset.filter(
                scheduled_at__date__lte=date_to
            )

        if search:
            queryset = queryset.filter(
                Q(lead__full_name__icontains=search)
                | Q(lead__phone__icontains=search)
                | Q(property__title__icontains=search)
                | Q(notes__icontains=search)
            )

        return queryset

    def perform_create(self, serializer):
        user = self.request.user
        lead = serializer.validated_data["lead"]

        if user.role == "agent":
            site_visit = serializer.save(
                agency=user.agency,
                assigned_agent=user,
                created_by=user
            )

            queue_site_visit_scheduled_email(site_visit)
            return

        assigned_agent = serializer.validated_data.get(
            "assigned_agent"
        )

        if assigned_agent is None:
            assigned_agent = lead.assigned_agent

        site_visit = serializer.save(
            agency=user.agency,
            assigned_agent=assigned_agent,
            created_by=user
        )

        queue_site_visit_scheduled_email(site_visit)


class SiteVisitDetailView(generics.RetrieveUpdateDestroyAPIView):
    serializer_class = SiteVisitSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return get_accessible_site_visits_for_user(
            self.request.user
        ).select_related(
            "agency",
            "lead",
            "property",
            "assigned_agent",
            "created_by",
        )
    
    def update(self, request, *args, **kwargs):
        site_visit_before_update = self.get_object()
        old_status = site_visit_before_update.status

        response = super().update(request, *args, **kwargs)

        site_visit_after_update = self.get_object()

        if (
            old_status != "scheduled"
            and site_visit_after_update.status == "scheduled"
        ):
            queue_site_visit_scheduled_email(site_visit_after_update)

        return response

    def destroy(self, request, *args, **kwargs):
        if user_can_manage_all_site_visits(request.user):
            return super().destroy(request, *args, **kwargs)

        raise PermissionDenied(
            "Only agency owners or managers can delete site visits."
        )
    

class PublicSiteVisitRequestView(APIView):
    permission_classes = [AllowAny]
    serializer_class = PublicSiteVisitRequestSerializer

    @transaction.atomic
    def post(self, request, property_id):
        property_obj = get_object_or_404(
            Property,
            id=property_id,
            is_published=True
        )

        serializer = PublicSiteVisitRequestSerializer(
            data=request.data
        )
        serializer.is_valid(raise_exception=True)

        data = serializer.validated_data

        assigned_agent = property_obj.assigned_agent

        preferred_location_parts = [
            property_obj.neighbourhood,
            property_obj.city,
            property_obj.district,
            property_obj.province,
        ]

        preferred_location = ", ".join(
            [
                part
                for part in preferred_location_parts
                if part
            ]
        )

        lead = Lead.objects.create(
            agency=property_obj.agency,
            assigned_agent=assigned_agent,
            full_name=data["full_name"],
            phone=data["phone"],
            email=data.get("email", ""),
            source="website",
            status="new",
            preferred_location=preferred_location,
            purpose=property_obj.purpose,
            property_type=property_obj.property_type,
            notes=data.get("message", ""),
        )

        lead_interest = LeadPropertyInterest.objects.create(
            agency=property_obj.agency,
            lead=lead,
            property=property_obj,
            interest_level="hot",
            notes="Requested site visit from public website.",
        )

        site_visit = SiteVisit.objects.create(
            agency=property_obj.agency,
            lead=lead,
            property=property_obj,
            assigned_agent=assigned_agent,
            scheduled_at=data["preferred_datetime"],
            status="requested",
            notes=data.get("message", ""),
            created_by=None,
        )

        LeadInteraction.objects.create(
            agency=property_obj.agency,
            lead=lead,
            agent=assigned_agent,
            interaction_type="site_visit",
            note=(
                "Public website visitor requested a site visit. "
                f"Preferred datetime: {data['preferred_datetime']}. "
                f"Message: {data.get('message', '')}"
            ),
            follow_up_date=data["preferred_datetime"],
        )

        return Response(
            {
                "message": "Site visit request submitted successfully.",
                "lead": {
                    "id": lead.id,
                    "full_name": lead.full_name,
                    "phone": lead.phone,
                    "assigned_agent": lead.assigned_agent_id,
                },
                "property": {
                    "id": property_obj.id,
                    "title": property_obj.title,
                },
                "site_visit": {
                    "id": site_visit.id,
                    "status": site_visit.status,
                    "scheduled_at": site_visit.scheduled_at,
                    "assigned_agent": site_visit.assigned_agent_id,
                },
                "lead_interest": {
                    "id": lead_interest.id,
                    "interest_level": lead_interest.interest_level,
                },
            },
            status=status.HTTP_201_CREATED,
        )