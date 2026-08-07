from django.db.models import Avg, F, Q
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

from .models import (
    Lead, LeadPropertyInterest, LeadInteraction, LeadStatusHistory,
    LeadAutomationSettings, LeadAssignmentRule, LeadDuplicateFlag,
    LeadAutomationEvent,
)
from .serializers import (
    LeadSerializer,
    LeadPropertyInterestSerializer,
    LeadInteractionSerializer,
    LeadStatusHistorySerializer,
    LeadAutomationSettingsSerializer,
    LeadAssignmentRuleSerializer,
    LeadDuplicateFlagSerializer,
    LeadAutomationEventSerializer,
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


def require_automation_manager(user):
    if not user.agency_id:
        raise PermissionDenied("An agency context is required for lead automation.")
    if user.role not in ["agency_owner", "agency_manager", "super_admin"]:
        raise PermissionDenied("Only owners or managers can configure lead automation.")

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
            "property_interests__property",
            "interactions",
            "inbox_conversations",
            "site_visits",
            "deals__offers",
            "deals__documents",
            "documents",
        ).order_by(F("last_contacted_at").desc(nulls_last=True), "-created_at")

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
        from .automation import apply_lead_automation
        apply_lead_automation(lead)


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
            "property_interests__property",
            "interactions",
            "inbox_conversations",
            "site_visits",
            "deals__offers",
            "deals__documents",
            "documents",
        )

    def perform_update(self, serializer):
        lead = self.get_object()
        previous_status = lead.status
        previous_agent = lead.assigned_agent
        previous_follow_up = lead.next_follow_up_at
        updated_lead = serializer.save()

        if previous_agent != updated_lead.assigned_agent:
            from .automation import get_automation_settings, stamp_assignment
            if updated_lead.assigned_agent:
                stamp_assignment(
                    updated_lead,
                    updated_lead.assigned_agent,
                    get_automation_settings(updated_lead.agency),
                    previous_agent=previous_agent,
                )
            else:
                updated_lead.assigned_at = None
                updated_lead.response_due_at = None
                updated_lead.assignment_responded_at = None
                updated_lead.save(update_fields=[
                    "assigned_at", "response_due_at", "assignment_responded_at", "updated_at"
                ])

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
        interest = serializer.save(
            agency=self.request.user.agency,
            lead=lead
        )
        if not lead.assigned_agent_id:
            from .automation import apply_lead_automation
            apply_lead_automation(lead, property_obj=interest.property)


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
        update_fields = []
        if interaction.direction != "internal":
            lead.last_contacted_at = timezone.now()
            update_fields.append("last_contacted_at")
        if interaction.follow_up_date:
            lead.next_follow_up_at = interaction.follow_up_date
            lead.follow_up_status = Lead.FOLLOW_UP_PENDING
            update_fields.extend(["next_follow_up_at", "follow_up_status"])
            lead.follow_up_reminder_sent_at = None
            lead.follow_up_reminder_error = ""
            update_fields.extend(
                ["follow_up_reminder_sent_at", "follow_up_reminder_error"]
            )
        if update_fields:
            update_fields.append("updated_at")
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
                "direction": request.data.get("direction", "outbound"),
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


class LeadWorkspaceView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, lead_id):
        from crm_inbox.models import SocialMessage
        from crm_inbox.serializers import ConversationSerializer, SocialMessageSerializer
        from operations.models import Deal, Document, Offer
        from operations.serializers import DealSerializer, DocumentSerializer, OfferSerializer

        lead = get_object_or_404(
            get_accessible_leads_for_user(request.user).select_related(
                "assigned_agent", "contact"
            ).prefetch_related(
                "property_interests__property", "interactions__agent",
                "status_history__changed_by", "site_visits__property",
                "inbox_conversations__contact", "deals__offers", "documents",
            ),
            id=lead_id,
        )
        deals = Deal.objects.filter(agency=lead.agency, lead=lead).select_related(
            "property", "assigned_agent", "contact"
        ).prefetch_related("offers")
        offers = Offer.objects.filter(agency=lead.agency, deal__lead=lead).select_related(
            "deal", "submitted_by"
        )
        documents = Document.objects.filter(agency=lead.agency).filter(
            Q(lead=lead) | Q(deal__lead=lead) | Q(contact__lead=lead)
        ).select_related("lead", "deal", "contact", "property", "uploaded_by").distinct()
        conversations = lead.inbox_conversations.select_related(
            "social_account", "contact", "assigned_agent", "linked_lead"
        ).all()
        social_messages = SocialMessage.objects.filter(
            conversation__linked_lead=lead
        ).select_related("conversation").order_by("-sent_at")

        return Response({
            "lead": LeadSerializer(lead, context={"request": request}).data,
            "property_interests": LeadPropertyInterestSerializer(
                lead.property_interests.all(), many=True, context={"request": request}
            ).data,
            "interactions": LeadInteractionSerializer(
                lead.interactions.all(), many=True, context={"request": request}
            ).data,
            "status_history": LeadStatusHistorySerializer(
                lead.status_history.all(), many=True
            ).data,
            "site_visits": SiteVisitSerializer(lead.site_visits.all(), many=True).data,
            "deals": DealSerializer(deals, many=True, context={"request": request}).data,
            "offers": OfferSerializer(offers, many=True, context={"request": request}).data,
            "documents": DocumentSerializer(documents, many=True, context={"request": request}).data,
            "conversations": ConversationSerializer(conversations, many=True).data,
            "social_messages": [
                {
                    **SocialMessageSerializer(message).data,
                    "conversation_id": message.conversation_id,
                    "platform": message.conversation.platform,
                }
                for message in social_messages
            ],
            "automation_events": LeadAutomationEventSerializer(
                lead.automation_events.select_related(
                    "rule", "from_agent", "to_agent"
                ).all()[:50], many=True
            ).data,
            "duplicate_flags": LeadDuplicateFlagSerializer(
                lead.duplicate_flags.select_related(
                    "candidate", "reviewed_by"
                ).all(), many=True
            ).data,
        })


class LeadDocumentListCreateView(generics.ListCreateAPIView):
    permission_classes = [IsAuthenticated]

    def get_serializer_class(self):
        from operations.serializers import DocumentSerializer
        return DocumentSerializer

    def get_lead(self):
        return get_object_or_404(
            get_accessible_leads_for_user(self.request.user),
            id=self.kwargs["lead_id"],
        )

    def get_queryset(self):
        from operations.models import Document
        return Document.objects.filter(
            agency=self.request.user.agency,
            lead=self.get_lead(),
        ).select_related("lead", "uploaded_by", "property", "deal", "contact", "owner")

    def perform_create(self, serializer):
        serializer.save(
            agency=self.request.user.agency,
            lead=self.get_lead(),
            uploaded_by=self.request.user,
        )


class LeadAutomationSettingsView(APIView):
    permission_classes = [IsAuthenticated]

    def get_object(self, request):
        if not request.user.agency_id:
            raise PermissionDenied("An agency context is required for lead automation.")
        settings_obj, _ = LeadAutomationSettings.objects.get_or_create(
            agency=request.user.agency
        )
        return settings_obj

    def get(self, request):
        return Response(LeadAutomationSettingsSerializer(self.get_object(request)).data)

    def patch(self, request):
        require_automation_manager(request.user)
        serializer = LeadAutomationSettingsSerializer(
            self.get_object(request), data=request.data, partial=True
        )
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)


class LeadAssignmentRuleListCreateView(generics.ListCreateAPIView):
    serializer_class = LeadAssignmentRuleSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return LeadAssignmentRule.objects.filter(
            agency=self.request.user.agency
        ).select_related("match_property", "assign_to_agent")

    def perform_create(self, serializer):
        require_automation_manager(self.request.user)
        serializer.save(agency=self.request.user.agency)


class LeadAssignmentRuleDetailView(generics.RetrieveUpdateDestroyAPIView):
    serializer_class = LeadAssignmentRuleSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return LeadAssignmentRule.objects.filter(
            agency=self.request.user.agency
        ).select_related("match_property", "assign_to_agent")

    def perform_update(self, serializer):
        require_automation_manager(self.request.user)
        serializer.save()

    def perform_destroy(self, instance):
        require_automation_manager(self.request.user)
        instance.delete()


class LeadDuplicateFlagListView(generics.ListAPIView):
    serializer_class = LeadDuplicateFlagSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        queryset = LeadDuplicateFlag.objects.filter(
            agency=self.request.user.agency
        ).select_related("lead", "candidate", "reviewed_by")
        status_value = self.request.query_params.get("status")
        if status_value:
            queryset = queryset.filter(status=status_value)
        if self.request.user.role == "agent":
            queryset = queryset.filter(
                Q(lead__assigned_agent=self.request.user)
                | Q(candidate__assigned_agent=self.request.user)
            )
        return queryset


class LeadDuplicateFlagReviewView(APIView):
    permission_classes = [IsAuthenticated]

    def patch(self, request, pk):
        require_automation_manager(request.user)
        duplicate = get_object_or_404(
            LeadDuplicateFlag, pk=pk, agency=request.user.agency
        )
        serializer = LeadDuplicateFlagSerializer(
            duplicate, data=request.data, partial=True
        )
        serializer.is_valid(raise_exception=True)
        serializer.save(reviewed_by=request.user, reviewed_at=timezone.now())
        return Response(serializer.data)


class LeadAutomationEventListView(generics.ListAPIView):
    serializer_class = LeadAutomationEventSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        queryset = LeadAutomationEvent.objects.filter(
            agency=self.request.user.agency
        ).select_related("lead", "rule", "from_agent", "to_agent")
        if self.request.user.role == "agent":
            queryset = queryset.filter(
                Q(lead__assigned_agent=self.request.user)
                | Q(from_agent=self.request.user)
                | Q(to_agent=self.request.user)
            ).distinct()
        return queryset[:100]


class LeadAutomationDashboardView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        from users.models import AgencyUser
        from .automation import ACTIVE_STATUSES

        now = timezone.now()
        agents = AgencyUser.objects.filter(
            agency=request.user.agency,
            role=AgencyUser.ROLE_AGENT,
            is_active=True,
        )
        if request.user.role == AgencyUser.ROLE_AGENT:
            agents = agents.filter(pk=request.user.pk)
        agent_rows = []
        for agent in agents.order_by("full_name"):
            leads = Lead.objects.filter(agency=request.user.agency, assigned_agent=agent)
            response_stats = leads.exclude(response_time_seconds__isnull=True).aggregate(
                average=Avg("response_time_seconds")
            )
            agent_rows.append({
                "id": agent.id,
                "name": agent.full_name,
                "active_leads": leads.filter(status__in=ACTIVE_STATUSES).count(),
                "awaiting_response": leads.filter(
                    status__in=ACTIVE_STATUSES,
                    assignment_responded_at__isnull=True,
                ).count(),
                "overdue_responses": leads.filter(
                    status__in=ACTIVE_STATUSES,
                    assignment_responded_at__isnull=True,
                    response_due_at__lt=now,
                ).count(),
                "neglected_leads": leads.filter(
                    status__in=ACTIVE_STATUSES,
                    neglect_alerted_at__isnull=False,
                ).count(),
                "average_response_seconds": round(response_stats["average"] or 0),
            })
        agency_leads = Lead.objects.filter(agency=request.user.agency)
        return Response({
            "summary": {
                "active_leads": agency_leads.filter(status__in=ACTIVE_STATUSES).count(),
                "unassigned_leads": agency_leads.filter(
                    status__in=ACTIVE_STATUSES, assigned_agent__isnull=True
                ).count(),
                "overdue_responses": agency_leads.filter(
                    status__in=ACTIVE_STATUSES,
                    assigned_agent__isnull=False,
                    assignment_responded_at__isnull=True,
                    response_due_at__lt=now,
                ).count(),
                "pending_duplicates": LeadDuplicateFlag.objects.filter(
                    agency=request.user.agency, status="pending"
                ).count(),
            },
            "agents": agent_rows,
        })


class LeadAutomationProcessView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        require_automation_manager(request.user)
        from .automation import process_lead_automation
        return Response(process_lead_automation(agency=request.user.agency))
