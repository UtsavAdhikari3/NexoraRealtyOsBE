from django.db.models import Q
from django.shortcuts import get_object_or_404

from rest_framework import generics
from rest_framework.permissions import IsAuthenticated

from drf_spectacular.utils import (
    extend_schema,
    extend_schema_view,
    OpenApiParameter,
)
from drf_spectacular.types import OpenApiTypes

from .models import Lead, LeadPropertyInterest, LeadInteraction
from .serializers import (
    LeadSerializer,
    LeadPropertyInterestSerializer,
    LeadInteractionSerializer,
)


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

        return queryset

    def perform_create(self, serializer):
        user = self.request.user

        if user.role == "agent":
            serializer.save(
                agency=user.agency,
                assigned_agent=user
            )
            return

        serializer.save(
            agency=user.agency
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
        queryset = LeadInteraction.objects.filter(
            agency=self.request.user.agency
        ).select_related(
            "lead",
            "agency",
            "agent",
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

        serializer.save(
            agency=self.request.user.agency,
            lead=lead,
            agent=self.request.user
        )


class LeadInteractionDetailView(generics.RetrieveUpdateDestroyAPIView):
    serializer_class = LeadInteractionSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return LeadInteraction.objects.filter(
            agency=self.request.user.agency
        ).select_related(
            "lead",
            "agency",
            "agent",
        )