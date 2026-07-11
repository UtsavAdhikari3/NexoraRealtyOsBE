from django.db.models import Q
from django.utils import timezone
from django.shortcuts import get_object_or_404

from rest_framework import generics
from rest_framework import status
from rest_framework.exceptions import PermissionDenied
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from drf_spectacular.utils import (
    extend_schema,
    extend_schema_view,
    OpenApiParameter,
)
from drf_spectacular.types import OpenApiTypes

from .models import Lead, LeadPropertyInterest, LeadInteraction, LeadStatusHistory
from .serializers import (
    LeadSerializer,
    LeadPropertyInterestSerializer,
    LeadInteractionSerializer,
    LeadStatusHistorySerializer,
)
from site_visits.serializers import SiteVisitSerializer


def get_accessible_leads_for_user(user):
    queryset = Lead.objects.filter(
        agency=user.agency
    )

    if user.role == "agent":
        queryset = queryset.filter(
            assigned_agent=user
        )

    return queryset

LEAD_FILTER_PARAMETERS = [
    OpenApiParameter(
        name="status",
        type=OpenApiTypes.STR,
        location=OpenApiParameter.QUERY,
        required=False,
        description="Filter by lead status. Example: new, contacted, interested, won, lost"
    ),
    OpenApiParameter(
        name="source",
        type=OpenApiTypes.STR,
        location=OpenApiParameter.QUERY,
        required=False,
        description="Filter by lead source. Example: website, facebook, whatsapp, manual"
    ),
    OpenApiParameter(
        name="assigned_agent",
        type=OpenApiTypes.STR,
        location=OpenApiParameter.QUERY,
        required=False,
        description="Filter by assigned agent ID, or use 'unassigned'"
    ),
    OpenApiParameter(
        name="property_type",
        type=OpenApiTypes.STR,
        location=OpenApiParameter.QUERY,
        required=False,
        description="Filter by preferred property type. Example: house, land, apartment"
    ),
    OpenApiParameter(
        name="purpose",
        type=OpenApiTypes.STR,
        location=OpenApiParameter.QUERY,
        required=False,
        description="Filter by purpose. Example: sale, rent, lease"
    ),
    OpenApiParameter(
        name="location",
        type=OpenApiTypes.STR,
        location=OpenApiParameter.QUERY,
        required=False,
        description="Search preferred location and interested property locations"
    ),
    OpenApiParameter(
        name="search",
        type=OpenApiTypes.STR,
        location=OpenApiParameter.QUERY,
        required=False,
        description="Search lead full name, phone, or email"
    ),
    OpenApiParameter(
        name="follow_up",
        type=OpenApiTypes.STR,
        location=OpenApiParameter.QUERY,
        required=False,
        description="Filter follow-ups: due_today, overdue, upcoming, none",
    ),
]


@extend_schema_view(
    get=extend_schema(parameters=LEAD_FILTER_PARAMETERS)
)
class LeadListCreateView(generics.ListCreateAPIView):
    serializer_class = LeadSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        queryset = get_accessible_leads_for_user(
                self.request.user).select_related(
            "agency",
            "assigned_agent",
        ).prefetch_related(
            "property_interests",
            "interactions",
        ).order_by("-created_at")

        status_value = self.request.query_params.get("status")
        source = self.request.query_params.get("source")
        assigned_agent = self.request.query_params.get("assigned_agent")
        property_type = self.request.query_params.get("property_type")
        purpose = self.request.query_params.get("purpose")
        location = self.request.query_params.get("location")
        search = self.request.query_params.get("search")
        follow_up = self.request.query_params.get("follow_up")

        if status_value and status_value != "all":
            queryset = queryset.filter(status=status_value)

        if source and source != "all":
            queryset = queryset.filter(source=source)

        if assigned_agent and assigned_agent != "all":
            if assigned_agent == "unassigned":
                queryset = queryset.filter(assigned_agent__isnull=True)
            elif assigned_agent.isdigit():
                queryset = queryset.filter(assigned_agent_id=int(assigned_agent))
            else:
                queryset = queryset.none()

        if property_type and property_type != "all":
            queryset = queryset.filter(property_type=property_type)

        if purpose and purpose != "all":
            queryset = queryset.filter(purpose=purpose)

        if location and location != "all":
            queryset = queryset.filter(
                Q(preferred_location__icontains=location)
                | Q(property_interests__property__province__icontains=location)
                | Q(property_interests__property__district__icontains=location)
                | Q(property_interests__property__city__icontains=location)
                | Q(property_interests__property__neighbourhood__icontains=location)
                | Q(property_interests__property__address__icontains=location)
            ).distinct()

        if search:
            queryset = queryset.filter(
                Q(full_name__icontains=search)
                | Q(phone__icontains=search)
                | Q(email__icontains=search)
            )

        now = timezone.now()
        if follow_up == "due_today":
            queryset = queryset.filter(
                follow_up_status=Lead.FOLLOW_UP_PENDING,
                next_follow_up_at__date=now.date(),
            )
        elif follow_up == "overdue":
            queryset = queryset.filter(
                follow_up_status=Lead.FOLLOW_UP_PENDING,
                next_follow_up_at__lt=now,
            )
        elif follow_up == "upcoming":
            queryset = queryset.filter(
                follow_up_status=Lead.FOLLOW_UP_PENDING,
                next_follow_up_at__gt=now,
            )
        elif follow_up == "none":
            queryset = queryset.filter(next_follow_up_at__isnull=True)

        return queryset

    def perform_create(self, serializer):
        user = self.request.user

        if user.role == "agent":
            lead = serializer.save(
                agency=user.agency,
                assigned_agent=user,
                created_by=user,
            )
        else:
            lead = serializer.save(
                agency=user.agency,
                created_by=user,
            )

        LeadStatusHistory.objects.create(
            agency=user.agency,
            lead=lead,
            to_status=lead.status,
            changed_by=user,
        )


class LeadDetailView(generics.RetrieveUpdateDestroyAPIView):
    serializer_class = LeadSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return get_accessible_leads_for_user(
            self.request.user
        ).select_related(
            "agency",
            "assigned_agent",
        ).prefetch_related(
            "property_interests",
            "interactions",
        )

    def perform_update(self, serializer):
        lead = self.get_object()
        previous_status = lead.status
        previous_follow_up = lead.next_follow_up_at
        updated_lead = serializer.save()

        if previous_follow_up != updated_lead.next_follow_up_at:
            updated_lead.follow_up_reminder_sent_at = None
            updated_lead.follow_up_reminder_error = ""
            updated_lead.save(
                update_fields=[
                    "follow_up_reminder_sent_at",
                    "follow_up_reminder_error",
                ]
            )

        if previous_status != updated_lead.status:
            LeadStatusHistory.objects.create(
                agency=updated_lead.agency,
                lead=updated_lead,
                from_status=previous_status,
                to_status=updated_lead.status,
                changed_by=self.request.user,
            )

    def destroy(self, request, *args, **kwargs):
        if request.user.role not in ["agency_owner", "agency_manager", "super_admin"]:
            raise PermissionDenied("Only owners or managers can delete leads.")
        return super().destroy(request, *args, **kwargs)


class LeadPropertyInterestListCreateView(generics.ListCreateAPIView):
    serializer_class = LeadPropertyInterestSerializer
    permission_classes = [IsAuthenticated]

    def get_lead(self):
        return get_object_or_404(
                get_accessible_leads_for_user(self.request.user),
                id=self.kwargs["lead_id"]
            )

    def get_queryset(self):
        lead = self.get_lead()

        return LeadPropertyInterest.objects.filter(
            agency=self.request.user.agency,
            lead=lead
        ).select_related(
            "property",
            "lead",
            "agency",
        ).order_by("-created_at")

    def get_serializer_context(self):
        context = super().get_serializer_context()
        context["lead"] = self.get_lead()

        return context

    def perform_create(self, serializer):
        lead = self.get_lead()

        serializer.save(
            agency=self.request.user.agency,
            lead=lead
        )


class LeadPropertyInterestDetailView(generics.RetrieveUpdateDestroyAPIView):
    serializer_class = LeadPropertyInterestSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        queryset = LeadPropertyInterest.objects.filter(
            agency=self.request.user.agency
        ).select_related(
            "lead",
            "agency",
            "property",
        )

        if self.request.user.role == "agent":
            queryset = queryset.filter(
                lead__assigned_agent=self.request.user
            )

        return queryset

class LeadInteractionListCreateView(generics.ListCreateAPIView):
    serializer_class = LeadInteractionSerializer
    permission_classes = [IsAuthenticated]

    def get_lead(self):
        return get_object_or_404(
            get_accessible_leads_for_user(self.request.user),
            id=self.kwargs["lead_id"]
        )

    def get_queryset(self):
        lead = self.get_lead()

        return LeadInteraction.objects.filter(
            agency=self.request.user.agency,
            lead=lead
        ).select_related(
            "lead",
            "agency",
            "agent",
        ).order_by("-created_at")

    def perform_create(self, serializer):
        lead = self.get_lead()

        interaction = serializer.save(
            agency=self.request.user.agency,
            lead=lead,
            agent=self.request.user
        )
        lead.last_contacted_at = timezone.now()
        update_fields = ["last_contacted_at", "updated_at"]
        if interaction.follow_up_date:
            lead.next_follow_up_at = interaction.follow_up_date
            lead.follow_up_status = Lead.FOLLOW_UP_PENDING
            update_fields.extend(["next_follow_up_at", "follow_up_status"])
            lead.follow_up_reminder_sent_at = None
            lead.follow_up_reminder_error = ""
            update_fields.extend(
                ["follow_up_reminder_sent_at", "follow_up_reminder_error"]
            )
        lead.save(update_fields=update_fields)


class LeadInteractionDetailView(generics.RetrieveUpdateDestroyAPIView):
    serializer_class = LeadInteractionSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        queryset = LeadInteraction.objects.filter(
            agency=self.request.user.agency
        ).select_related(
            "lead",
            "agency",
            "agent",
        )

        if self.request.user.role == "agent":
            queryset = queryset.filter(lead__assigned_agent=self.request.user)

        return queryset


class LeadFollowUpCompleteView(APIView):
    permission_classes = [IsAuthenticated]
    serializer_class = LeadSerializer

    def post(self, request, lead_id):
        lead = get_object_or_404(
            get_accessible_leads_for_user(request.user),
            id=lead_id,
        )
        note = str(request.data.get("note", "Follow-up completed.")).strip()
        next_follow_up_at = request.data.get("next_follow_up_at")

        interaction_serializer = LeadInteractionSerializer(
            data={
                "interaction_type": request.data.get("interaction_type", "note"),
                "note": note,
                "follow_up_date": next_follow_up_at,
            },
            context={"request": request},
        )
        interaction_serializer.is_valid(raise_exception=True)
        interaction_serializer.save(
            agency=lead.agency,
            lead=lead,
            agent=request.user,
        )

        lead.last_contacted_at = timezone.now()
        lead.next_follow_up_at = interaction_serializer.validated_data.get("follow_up_date")
        lead.follow_up_status = (
            Lead.FOLLOW_UP_PENDING
            if lead.next_follow_up_at
            else Lead.FOLLOW_UP_COMPLETED
        )
        lead.follow_up_reminder_sent_at = None
        lead.follow_up_reminder_error = ""
        lead.save(
            update_fields=[
                "last_contacted_at",
                "next_follow_up_at",
                "follow_up_status",
                "follow_up_reminder_sent_at",
                "follow_up_reminder_error",
                "updated_at",
            ]
        )

        return Response(LeadSerializer(lead, context={"request": request}).data)


class LeadTimelineView(APIView):
    permission_classes = [IsAuthenticated]
    serializer_class = LeadSerializer

    def get(self, request, lead_id):
        lead = get_object_or_404(
            get_accessible_leads_for_user(request.user),
            id=lead_id,
        )
        interactions = lead.interactions.select_related("agent").all()
        history = lead.status_history.select_related("changed_by").all()
        site_visits = lead.site_visits.select_related(
            "property", "assigned_agent", "created_by"
        ).all()

        return Response(
            {
                "interactions": LeadInteractionSerializer(interactions, many=True).data,
                "status_history": LeadStatusHistorySerializer(history, many=True).data,
                "site_visits": SiteVisitSerializer(site_visits, many=True).data,
            }
        )
