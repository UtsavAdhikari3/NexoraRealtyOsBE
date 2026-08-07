from datetime import datetime, timedelta, timezone as dt_timezone
from decimal import Decimal
import hashlib
import hmac
import json

import requests
from django.conf import settings
from django.core.mail import send_mail
from django.db import transaction
from django.db.models import Count, Q, Sum
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action, api_view, permission_classes, throttle_classes
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import AnonRateThrottle
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema

from agencies.models import Agency
from agencies.public_views import get_public_agencies_queryset
from leads.models import Lead, LeadInteraction
from leads.services import get_or_create_public_lead
from properties.models import Property
from users.models import AgencyUser
from .models import (
    AgentReview, Appointment, AppointmentAvailability, AuditLog, Contact, CustomerProfile,
    CustomFieldDefinition, Deal, Document, Invitation, Lease, Notification,
    Offer, Owner, PipelineStage, PublicSubmission, SavedProperty, SavedSearch,
    Subscription, SubscriptionPlan, Task,
)
from .serializers import (
    AgentReviewSerializer, AppointmentAvailabilitySerializer, AppointmentSerializer, AuditLogSerializer,
    ContactSerializer, CustomerLoginSerializer, CustomerProfileSerializer, CustomerRegistrationSerializer,
    CustomFieldDefinitionSerializer, DealSerializer, DocumentSerializer,
    InvitationAcceptSerializer, InvitationSerializer, LeaseSerializer,
    NotificationSerializer, OfferSerializer, OwnerSerializer,
    PipelineStageSerializer, PublicAgentReviewSerializer, PublicSubmissionSerializer,
    SavedPropertySerializer, SavedSearchSerializer,
    SubscriptionPlanSerializer, SubscriptionSerializer, TaskSerializer,
    TeamMemberSerializer,
    PlatformAgencySerializer,
)


MANAGER_ROLES = {AgencyUser.ROLE_AGENCY_OWNER, AgencyUser.ROLE_AGENCY_MANAGER, AgencyUser.ROLE_SUPER_ADMIN}


class PublicSubmissionRateThrottle(AnonRateThrottle):
    scope = "public_submission"


def client_ip(request):
    forwarded = request.META.get("HTTP_X_FORWARDED_FOR", "")
    return (forwarded.split(",")[0].strip() if forwarded else request.META.get("REMOTE_ADDR")) or None


def create_audit(request, instance, action):
    agency = instance if isinstance(instance, Agency) else (getattr(instance, "agency", None) or getattr(request.user, "agency", None))
    if not agency:
        return
    AuditLog.objects.create(
        agency=agency,
        actor=request.user if request.user.is_authenticated else None,
        action=action,
        entity_type=instance._meta.model_name,
        entity_id=str(instance.pk),
        summary=f"{action.title()} {instance._meta.verbose_name} {instance}",
        ip_address=client_ip(request),
    )


class AgencyModelViewSet(viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated]
    search_fields = ()

    def get_queryset(self):
        queryset = self.queryset
        user = self.request.user
        if user.role == AgencyUser.ROLE_SUPER_ADMIN:
            agency_id = self.request.query_params.get("agency")
            return queryset.filter(agency_id=agency_id) if agency_id else queryset
        if not user.agency_id:
            return queryset.none()
        queryset = queryset.filter(agency=user.agency)
        if user.role == AgencyUser.ROLE_AGENT:
            queryset = self.restrict_agent_queryset(queryset, user)
        search = self.request.query_params.get("search", "").strip()
        if search and self.search_fields:
            query = Q()
            for field in self.search_fields:
                query |= Q(**{f"{field}__icontains": search})
            queryset = queryset.filter(query)
        return queryset

    def restrict_agent_queryset(self, queryset, user):
        return queryset

    def perform_create(self, serializer):
        if not self.request.user.agency_id:
            raise ValidationError("An agency is required.")
        instance = serializer.save(agency=self.request.user.agency)
        create_audit(self.request, instance, "created")

    def perform_update(self, serializer):
        instance = serializer.save()
        create_audit(self.request, instance, "updated")

    def perform_destroy(self, instance):
        if self.request.user.role not in MANAGER_ROLES:
            raise PermissionDenied("Only owners and managers can delete records.")
        create_audit(self.request, instance, "deleted")
        instance.delete()


class PublicSubmissionViewSet(AgencyModelViewSet):
    queryset = PublicSubmission.objects.select_related("property", "agent", "lead")
    serializer_class = PublicSubmissionSerializer
    search_fields = ("full_name", "email", "phone", "message")

    def get_queryset(self):
        queryset = super().get_queryset()
        kind = self.request.query_params.get("kind")
        status_value = self.request.query_params.get("status")
        if kind:
            queryset = queryset.filter(kind=kind)
        if status_value:
            queryset = queryset.filter(status=status_value)
        return queryset

    def restrict_agent_queryset(self, queryset, user):
        return queryset.filter(Q(agent=user) | Q(lead__assigned_agent=user))

    def perform_update(self, serializer):
        previous_status = serializer.instance.status
        instance = serializer.save()
        if instance.status in {"completed", "spam"} and previous_status != instance.status:
            instance.processed_at = timezone.now()
            instance.save(update_fields=["processed_at", "updated_at"])
        create_audit(self.request, instance, "updated")


class AgentReviewViewSet(AgencyModelViewSet):
    queryset = AgentReview.objects.select_related("agent", "approved_by")
    serializer_class = AgentReviewSerializer
    search_fields = ("reviewer_name", "reviewer_email", "title", "comment")

    def restrict_agent_queryset(self, queryset, user):
        return queryset.filter(agent=user)

    def perform_update(self, serializer):
        approving = serializer.validated_data.get("is_approved")
        if approving is not None and self.request.user.role not in MANAGER_ROLES:
            raise PermissionDenied("Only owners or managers can moderate reviews.")
        moderation_fields = {}
        if approving is not None:
            moderation_fields = {
                "approved_by": self.request.user if approving else None,
                "approved_at": timezone.now() if approving else None,
            }
        instance = serializer.save(**moderation_fields)
        create_audit(self.request, instance, "updated")


class ContactViewSet(AgencyModelViewSet):
    queryset = Contact.objects.select_related("assigned_to", "lead")
    serializer_class = ContactSerializer
    search_fields = ("full_name", "email", "phone", "company")

    def restrict_agent_queryset(self, queryset, user):
        return queryset.filter(Q(assigned_to=user) | Q(lead__assigned_agent=user))

    def perform_create(self, serializer):
        assigned = self.request.user if self.request.user.role == AgencyUser.ROLE_AGENT else serializer.validated_data.get("assigned_to")
        instance = serializer.save(agency=self.request.user.agency, assigned_to=assigned)
        create_audit(self.request, instance, "created")

    @action(detail=False, methods=["post"], url_path="import-leads")
    def import_leads(self, request):
        leads = Lead.objects.filter(agency=request.user.agency).exclude(contact__isnull=False)
        if request.user.role == AgencyUser.ROLE_AGENT:
            leads = leads.filter(assigned_agent=request.user)
        created = 0
        for lead in leads:
            Contact.objects.create(
                agency=lead.agency, lead=lead, full_name=lead.full_name,
                email=lead.email, phone=lead.phone, source=lead.source,
                contact_type="buyer", assigned_to=lead.assigned_agent,
            )
            created += 1
        return Response({"created": created})


class OwnerViewSet(AgencyModelViewSet):
    queryset = Owner.objects.prefetch_related("properties").select_related("contact")
    serializer_class = OwnerSerializer
    search_fields = ("full_name", "email", "phone")

    def restrict_agent_queryset(self, queryset, user):
        return queryset.filter(properties__assigned_agent=user).distinct()


class DealViewSet(AgencyModelViewSet):
    queryset = Deal.objects.select_related("lead", "contact", "property", "assigned_agent").prefetch_related("offers")
    serializer_class = DealSerializer
    search_fields = ("title", "lead__full_name", "contact__full_name", "property__title")

    def get_queryset(self):
        queryset = super().get_queryset()
        stage = self.request.query_params.get("stage")
        return queryset.filter(stage=stage) if stage and stage != "all" else queryset

    def restrict_agent_queryset(self, queryset, user):
        return queryset.filter(Q(assigned_agent=user) | Q(lead__assigned_agent=user))

    def perform_create(self, serializer):
        assigned = self.request.user if self.request.user.role == AgencyUser.ROLE_AGENT else serializer.validated_data.get("assigned_agent")
        instance = serializer.save(agency=self.request.user.agency, assigned_agent=assigned)
        create_audit(self.request, instance, "created")
        if instance.assigned_agent:
            Notification.objects.create(agency=instance.agency, user=instance.assigned_agent, title="Deal assigned", message=instance.title, category="deal", link=f"/deals?deal={instance.id}")


class OfferViewSet(AgencyModelViewSet):
    queryset = Offer.objects.select_related("deal", "submitted_by")
    serializer_class = OfferSerializer

    def get_queryset(self):
        queryset = super().get_queryset()
        deal_id = self.request.query_params.get("deal")
        return queryset.filter(deal_id=deal_id) if deal_id else queryset

    def restrict_agent_queryset(self, queryset, user):
        return queryset.filter(deal__assigned_agent=user)

    def perform_create(self, serializer):
        instance = serializer.save(agency=self.request.user.agency, submitted_by=self.request.user)
        create_audit(self.request, instance, "created")
        if instance.deal.assigned_agent and instance.deal.assigned_agent != self.request.user:
            Notification.objects.create(agency=instance.agency, user=instance.deal.assigned_agent, title="New offer", message=f"{instance.currency} {instance.amount} for {instance.deal.title}", category="offer", link=f"/deals?deal={instance.deal_id}")

    @action(detail=True, methods=["post"])
    def respond(self, request, pk=None):
        offer = self.get_object()
        response_status = request.data.get("status")
        if response_status not in {"accepted", "rejected", "countered", "withdrawn"}:
            raise ValidationError({"status": "Choose accepted, rejected, countered, or withdrawn."})
        offer.status = response_status
        offer.responded_at = timezone.now()
        offer.save(update_fields=["status", "responded_at", "updated_at"])
        if response_status == "accepted":
            offer.deal.value = offer.amount
            offer.deal.stage = "contract"
            offer.deal.save(update_fields=["value", "stage", "updated_at"])
        create_audit(request, offer, response_status)
        return Response(self.get_serializer(offer).data)


class DocumentViewSet(AgencyModelViewSet):
    queryset = Document.objects.select_related("uploaded_by", "lead", "property", "deal", "contact", "owner")
    serializer_class = DocumentSerializer
    search_fields = ("title", "description")

    def restrict_agent_queryset(self, queryset, user):
        return queryset.filter(Q(uploaded_by=user) | Q(lead__assigned_agent=user) | Q(deal__assigned_agent=user) | Q(property__assigned_agent=user)).distinct()

    def perform_create(self, serializer):
        instance = serializer.save(agency=self.request.user.agency, uploaded_by=self.request.user)
        create_audit(self.request, instance, "created")


class LeaseViewSet(AgencyModelViewSet):
    queryset = Lease.objects.select_related("property", "tenant", "owner", "assigned_agent")
    serializer_class = LeaseSerializer
    search_fields = ("property__title", "tenant__full_name", "owner__full_name")

    def restrict_agent_queryset(self, queryset, user):
        return queryset.filter(assigned_agent=user)

    def perform_create(self, serializer):
        assigned = self.request.user if self.request.user.role == AgencyUser.ROLE_AGENT else serializer.validated_data.get("assigned_agent")
        instance = serializer.save(agency=self.request.user.agency, assigned_agent=assigned)
        create_audit(self.request, instance, "created")


class TaskViewSet(AgencyModelViewSet):
    queryset = Task.objects.select_related("assigned_to", "created_by", "lead", "deal", "property")
    serializer_class = TaskSerializer
    search_fields = ("title", "description")

    def get_queryset(self):
        queryset = super().get_queryset()
        status_value = self.request.query_params.get("status")
        due = self.request.query_params.get("due")
        if status_value and status_value != "all":
            queryset = queryset.filter(status=status_value)
        now = timezone.now()
        if due == "overdue": queryset = queryset.filter(due_at__lt=now).exclude(status="done")
        if due == "today": queryset = queryset.filter(due_at__date=now.date())
        if due == "upcoming": queryset = queryset.filter(due_at__gt=now)
        return queryset

    def restrict_agent_queryset(self, queryset, user):
        return queryset.filter(Q(assigned_to=user) | Q(created_by=user))

    def perform_create(self, serializer):
        assigned = self.request.user if self.request.user.role == AgencyUser.ROLE_AGENT else (serializer.validated_data.get("assigned_to") or self.request.user)
        instance = serializer.save(agency=self.request.user.agency, created_by=self.request.user, assigned_to=assigned)
        create_audit(self.request, instance, "created")
        if assigned != self.request.user:
            Notification.objects.create(agency=instance.agency, user=assigned, title="New task", message=instance.title, category="task", link="/tasks")


class NotificationViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Notification.objects.none()
    permission_classes = [IsAuthenticated]
    serializer_class = NotificationSerializer

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return self.queryset
        return Notification.objects.filter(user=self.request.user)

    @action(detail=True, methods=["post"])
    def read(self, request, pk=None):
        item = self.get_object(); item.is_read = True; item.save(update_fields=["is_read"])
        return Response(self.get_serializer(item).data)

    @action(detail=False, methods=["post"], url_path="read-all")
    def read_all(self, request):
        count = self.get_queryset().filter(is_read=False).update(is_read=True)
        return Response({"updated": count})


class InvitationViewSet(AgencyModelViewSet):
    queryset = Invitation.objects.select_related("invited_by")
    serializer_class = InvitationSerializer

    def initial(self, request, *args, **kwargs):
        super().initial(request, *args, **kwargs)
        if request.user.role not in MANAGER_ROLES:
            raise PermissionDenied("Only owners and managers can manage invitations.")

    def perform_create(self, serializer):
        instance = serializer.save(agency=self.request.user.agency, invited_by=self.request.user, expires_at=timezone.now() + timedelta(days=7))
        create_audit(self.request, instance, "invited")
        invite_url = f"{getattr(settings, 'FRONTEND_INVITE_URL', 'http://localhost:5173/accept-invitation')}?token={instance.token}"
        try:
            send_mail(
                f"You are invited to {instance.agency.name}",
                f"{instance.invited_by.full_name} invited you to Nexora RealtyOS as {instance.get_role_display()}. Accept your invitation: {invite_url}",
                settings.DEFAULT_FROM_EMAIL,
                [instance.email],
                fail_silently=False,
            )
        except Exception as exc:
            instance.delivery_error = str(exc)[:2000]
            instance.save(update_fields=["delivery_error"])


class TeamMemberViewSet(
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    mixins.UpdateModelMixin,
    viewsets.GenericViewSet,
):
    permission_classes = [IsAuthenticated]
    serializer_class = TeamMemberSerializer
    queryset = AgencyUser.objects.none()

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return self.queryset
        if self.request.user.role not in MANAGER_ROLES:
            raise PermissionDenied("Only owners and managers can manage team access.")
        if self.request.user.role == AgencyUser.ROLE_SUPER_ADMIN:
            agency_id = self.request.query_params.get("agency")
            return AgencyUser.objects.filter(agency_id=agency_id) if agency_id else AgencyUser.objects.exclude(agency__isnull=True)
        return AgencyUser.objects.filter(agency=self.request.user.agency).order_by("full_name")

    def perform_update(self, serializer):
        member = self.get_object()
        new_role = serializer.validated_data.get("role", member.role)
        new_active = serializer.validated_data.get("is_active", member.is_active)
        if member == self.request.user and (not new_active or new_role != member.role):
            raise ValidationError("You cannot deactivate or change your own role.")
        if member.role == AgencyUser.ROLE_AGENCY_OWNER and (not new_active or new_role != AgencyUser.ROLE_AGENCY_OWNER):
            other_owners = AgencyUser.objects.filter(agency=member.agency, role=AgencyUser.ROLE_AGENCY_OWNER, is_active=True).exclude(id=member.id)
            if not other_owners.exists():
                raise ValidationError("An agency must retain at least one active owner.")
        updated = serializer.save()
        create_audit(self.request, updated, "access_updated")


class PlatformAgencyViewSet(
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    mixins.UpdateModelMixin,
    viewsets.GenericViewSet,
):
    permission_classes = [IsAuthenticated]
    serializer_class = PlatformAgencySerializer
    queryset = Agency.objects.prefetch_related("users", "properties").order_by("-created_at")

    def get_queryset(self):
        if not getattr(self, "swagger_fake_view", False) and self.request.user.role != AgencyUser.ROLE_SUPER_ADMIN:
            raise PermissionDenied("Super admin access required.")
        queryset = self.queryset
        search = self.request.query_params.get("search", "").strip()
        return queryset.filter(Q(name__icontains=search) | Q(license_number__icontains=search)) if search else queryset

    def perform_update(self, serializer):
        agency = serializer.save()
        if agency.payment_status == Agency.PAYMENT_PAID and not agency.paid_at:
            agency.paid_at = timezone.now()
            agency.save(update_fields=["paid_at"])
        create_audit(self.request, agency, "platform_updated")


class CustomFieldViewSet(AgencyModelViewSet):
    queryset = CustomFieldDefinition.objects.all()
    serializer_class = CustomFieldDefinitionSerializer

    def get_queryset(self):
        queryset = super().get_queryset()
        module = self.request.query_params.get("module")
        return queryset.filter(module=module) if module else queryset


class PipelineStageViewSet(AgencyModelViewSet):
    queryset = PipelineStage.objects.all()
    serializer_class = PipelineStageSerializer

    def get_queryset(self):
        queryset = super().get_queryset()
        module = self.request.query_params.get("module")
        return queryset.filter(module=module) if module else queryset


class AuditLogViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = AuditLog.objects.none()
    permission_classes = [IsAuthenticated]
    serializer_class = AuditLogSerializer

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return self.queryset
        user = self.request.user
        if user.role not in MANAGER_ROLES:
            raise PermissionDenied("Only owners and managers can view audit logs.")
        queryset = AuditLog.objects.select_related("actor")
        if user.role != AgencyUser.ROLE_SUPER_ADMIN:
            queryset = queryset.filter(agency=user.agency)
        entity_type = self.request.query_params.get("entity_type")
        return queryset.filter(entity_type=entity_type) if entity_type else queryset


class AppointmentAvailabilityViewSet(AgencyModelViewSet):
    queryset = AppointmentAvailability.objects.select_related("agent")
    serializer_class = AppointmentAvailabilitySerializer

    def restrict_agent_queryset(self, queryset, user):
        return queryset.filter(agent=user)

    def perform_create(self, serializer):
        agent = self.request.user if self.request.user.role == AgencyUser.ROLE_AGENT else serializer.validated_data.get("agent")
        if not agent:
            raise ValidationError({"agent": "Agent is required."})
        instance = serializer.save(agency=self.request.user.agency, agent=agent)
        create_audit(self.request, instance, "created")


class AppointmentViewSet(AgencyModelViewSet):
    queryset = Appointment.objects.select_related("agent", "property", "customer")
    serializer_class = AppointmentSerializer
    search_fields = ("full_name", "email", "phone", "property__title")

    def restrict_agent_queryset(self, queryset, user):
        return queryset.filter(agent=user)


class SubscriptionViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Subscription.objects.none()
    permission_classes = [IsAuthenticated]
    serializer_class = SubscriptionSerializer

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return self.queryset
        if not self.request.user.agency_id:
            return Subscription.objects.none()
        return Subscription.objects.filter(agency=self.request.user.agency).select_related("plan").prefetch_related("payments")

    @action(detail=False, methods=["post"])
    def checkout(self, request):
        plan = get_object_or_404(SubscriptionPlan, code=request.data.get("plan"), is_active=True)
        secret = getattr(settings, "STRIPE_SECRET_KEY", "")
        price_id = getattr(settings, "STRIPE_PRICE_IDS", {}).get(plan.code)
        if not secret or not price_id:
            return Response({"detail": "Stripe checkout is not configured for this plan."}, status=status.HTTP_503_SERVICE_UNAVAILABLE)
        payload = [
            ("mode", "subscription"), ("line_items[0][price]", price_id), ("line_items[0][quantity]", "1"),
            ("success_url", getattr(settings, "STRIPE_SUCCESS_URL", "http://localhost:5173/settings?checkout=success")),
            ("cancel_url", getattr(settings, "STRIPE_CANCEL_URL", "http://localhost:5173/settings?checkout=cancelled")),
            ("client_reference_id", str(request.user.agency_id)),
            ("customer_email", request.user.email),
            ("metadata[agency_id]", str(request.user.agency_id)),
            ("metadata[plan_code]", plan.code),
            ("subscription_data[metadata][agency_id]", str(request.user.agency_id)),
            ("subscription_data[metadata][plan_code]", plan.code),
        ]
        response = requests.post("https://api.stripe.com/v1/checkout/sessions", data=payload, auth=(secret, ""), timeout=15)
        if not response.ok:
            return Response({"detail": "Unable to create checkout session.", "provider_error": response.json().get("error", {}).get("message")}, status=status.HTTP_502_BAD_GATEWAY)
        return Response({"checkout_url": response.json()["url"], "session_id": response.json()["id"]})

    @action(detail=False, methods=["post"], url_path="billing-portal")
    def billing_portal(self, request):
        subscription = self.get_queryset().first()
        if not subscription or not subscription.provider_customer_id:
            raise ValidationError("No Stripe customer exists for this agency.")
        secret = getattr(settings, "STRIPE_SECRET_KEY", "")
        if not secret:
            return Response({"detail": "Stripe billing is not configured."}, status=status.HTTP_503_SERVICE_UNAVAILABLE)
        response = requests.post(
            "https://api.stripe.com/v1/billing_portal/sessions",
            data={"customer": subscription.provider_customer_id, "return_url": getattr(settings, "STRIPE_SUCCESS_URL", "http://localhost:5173/billing")},
            auth=(secret, ""),
            timeout=15,
        )
        if not response.ok:
            return Response({"detail": "Unable to create billing portal session."}, status=status.HTTP_502_BAD_GATEWAY)
        return Response({"portal_url": response.json()["url"]})


@extend_schema(request=InvitationAcceptSerializer, responses={201: OpenApiTypes.OBJECT})
@api_view(["POST"])
@permission_classes([AllowAny])
def accept_invitation(request):
    serializer = InvitationAcceptSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    invite = get_object_or_404(Invitation, token=serializer.validated_data["token"], accepted_at__isnull=True)
    if invite.expires_at <= timezone.now():
        return Response({"detail": "Invitation has expired."}, status=status.HTTP_410_GONE)
    if AgencyUser.objects.filter(email__iexact=invite.email).exists():
        raise ValidationError({"email": "An account already exists for this email."})
    with transaction.atomic():
        user = AgencyUser.objects.create_user(email=invite.email, password=serializer.validated_data["password"], full_name=invite.full_name, role=invite.role, agency=invite.agency, is_email_verified=True)
        invite.accepted_at = timezone.now(); invite.save(update_fields=["accepted_at"])
    return Response({"id": user.id, "email": user.email, "role": user.role}, status=status.HTTP_201_CREATED)


@extend_schema(responses=OpenApiTypes.OBJECT)
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def report_summary(request):
    agency = request.user.agency
    if not agency:
        raise ValidationError("Agency required.")
    deals = Deal.objects.filter(agency=agency)
    leads = Lead.objects.filter(agency=agency)
    properties = Property.objects.filter(agency=agency)
    tasks = Task.objects.filter(agency=agency)
    if request.user.role == AgencyUser.ROLE_AGENT:
        deals = deals.filter(assigned_agent=request.user); leads = leads.filter(assigned_agent=request.user); properties = properties.filter(assigned_agent=request.user); tasks = tasks.filter(assigned_to=request.user)
    stage_rows = list(deals.values("stage").annotate(count=Count("id"), value=Sum("value")).order_by("stage"))
    source_rows = list(leads.values("source").annotate(count=Count("id")).order_by("source"))
    agent_rows = list(deals.values("assigned_agent__id", "assigned_agent__full_name").annotate(count=Count("id"), value=Sum("value"), commission=Sum("commission_amount")).order_by("-value"))
    won = deals.filter(stage="closed_won")
    return Response({
        "pipeline": stage_rows, "lead_sources": source_rows, "agent_performance": agent_rows,
        "totals": {"leads": leads.count(), "properties": properties.count(), "deals": deals.count(), "won_deals": won.count(), "won_value": won.aggregate(total=Sum("value"))["total"] or 0, "open_tasks": tasks.exclude(status__in=["done", "cancelled"]).count()},
    })


@extend_schema(responses=OpenApiTypes.OBJECT)
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def lead_matches(request, lead_id):
    lead = get_object_or_404(Lead, id=lead_id, agency=request.user.agency)
    if request.user.role == AgencyUser.ROLE_AGENT and lead.assigned_agent_id != request.user.id:
        raise PermissionDenied()
    queryset = Property.objects.filter(agency=lead.agency, status="available", is_published=True)
    results = []
    for item in queryset.select_related("assigned_agent").prefetch_related("media"):
        score, reasons = 0, []
        if lead.property_type and item.property_type == lead.property_type: score += 30; reasons.append("Property type")
        if lead.purpose and item.purpose == lead.purpose: score += 25; reasons.append("Purpose")
        location = lead.preferred_location.lower().strip()
        if location and any(location in str(value).lower() for value in [item.city, item.district, item.neighbourhood]): score += 25; reasons.append("Location")
        if lead.budget_min is not None and item.price >= lead.budget_min: score += 10; reasons.append("Above minimum budget")
        if lead.budget_max is not None and item.price <= lead.budget_max: score += 10; reasons.append("Within maximum budget")
        if score:
            primary = next((m for m in item.media.all() if m.is_primary), None)
            results.append({"property_id": item.id, "title": item.title, "price": item.price, "currency": item.currency, "location": ", ".join(filter(None, [item.neighbourhood, item.city])), "score": score, "reasons": reasons, "image": request.build_absolute_uri(primary.file.url) if primary and primary.file else None})
    return Response(sorted(results, key=lambda row: row["score"], reverse=True))


@extend_schema(responses=OpenApiTypes.OBJECT)
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def compare_properties(request):
    ids = [value for value in request.query_params.get("ids", "").split(",") if value.isdigit()][:4]
    items = Property.objects.filter(agency=request.user.agency, id__in=ids).prefetch_related("media")
    data = [{"id": p.id, "title": p.title, "price": p.price, "currency": p.currency, "property_type": p.property_type, "purpose": p.purpose, "city": p.city, "district": p.district, "bedrooms": p.bedrooms, "bathrooms": p.bathrooms, "land_area_value": p.land_area_value, "land_area_unit": p.land_area_unit, "built_up_area_value": p.built_up_area_value, "built_up_area_unit": p.built_up_area_unit, "amenities": p.amenities} for p in items]
    return Response(data)


@extend_schema(responses=OpenApiTypes.OBJECT)
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def admin_summary(request):
    if request.user.role != AgencyUser.ROLE_SUPER_ADMIN:
        raise PermissionDenied("Super admin access required.")
    return Response({
        "agencies": Agency.objects.count(), "active_agencies": Agency.objects.filter(is_active=True).count(),
        "users": AgencyUser.objects.count(), "properties": Property.objects.count(), "leads": Lead.objects.count(),
        "subscriptions": list(Subscription.objects.values("status").annotate(count=Count("id"))),
        "recent_agencies": list(Agency.objects.order_by("-created_at").values("id", "name", "payment_status", "is_active", "created_at")[:10]),
    })


def customer_from_request(request, agency):
    token = request.headers.get("X-Customer-Token") or request.query_params.get("customer_token")
    return get_object_or_404(CustomerProfile, agency=agency, access_token=token)


@extend_schema(request=PublicSubmissionSerializer, responses={201: OpenApiTypes.OBJECT})
@api_view(["POST"])
@permission_classes([AllowAny])
@throttle_classes([PublicSubmissionRateThrottle])
@transaction.atomic
def public_submission_create(request, slug):
    agency = get_object_or_404(get_public_agencies_queryset(), slug=slug)
    payload = request.data.copy()
    payload.pop("status", None)
    serializer = PublicSubmissionSerializer(data=payload, context={"request": request})
    serializer.is_valid(raise_exception=True)
    data = serializer.validated_data
    property_obj = data.get("property")
    agent = data.get("agent") or getattr(property_obj, "assigned_agent", None)

    if property_obj and property_obj.agency_id != agency.id:
        raise ValidationError({"property": "Property does not belong to this agency."})
    if agent and agent.agency_id != agency.id:
        raise ValidationError({"agent": "Agent does not belong to this agency."})

    metadata = data.get("metadata") or {}
    message = data.get("message", "")
    lead = None
    if data.get("phone"):
        lead_notes = message
        if metadata:
            lead_notes = f"{message}\n\nWebsite submission details: {json.dumps(metadata, ensure_ascii=False)}".strip()
        lead, _ = get_or_create_public_lead(
            agency=agency,
            assigned_agent=agent,
            full_name=data.get("full_name") or data.get("email") or "Website visitor",
            phone=data["phone"],
            email=data.get("email", ""),
            preferred_location=metadata.get("location") or metadata.get("address", ""),
            purpose=metadata.get("purpose", ""),
            property_type=metadata.get("property_type", ""),
            notes=lead_notes,
        )
        custom_data = dict(lead.custom_data or {})
        custom_data.update({"public_submission_kind": data["kind"], **metadata})
        lead.custom_data = custom_data
        lead.save(update_fields=["custom_data", "updated_at"])
        LeadInteraction.objects.create(
            agency=agency,
            lead=lead,
            agent=agent,
            interaction_type="note",
            direction="inbound",
            note=message or f"Public {data['kind'].replace('_', ' ')} submission received.",
        )

    submission = serializer.save(
        agency=agency,
        agent=agent,
        lead=lead,
        ip_address=client_ip(request),
        user_agent=request.headers.get("User-Agent", "")[:500],
    )
    if submission.kind == "listing_report" and submission.property:
        from properties.freshness import record_property_history
        record_property_history(
            submission.property, "report_received", "Public listing report received",
            changes={"submission_id": submission.id, "reason": submission.metadata.get("reason", "")},
            note=submission.message,
        )

    recipients = AgencyUser.objects.filter(agency=agency, is_active=True)
    if agent:
        recipients = recipients.filter(Q(id=agent.id) | Q(role__in=[AgencyUser.ROLE_AGENCY_OWNER, AgencyUser.ROLE_AGENCY_MANAGER]))
    else:
        recipients = recipients.filter(role__in=[AgencyUser.ROLE_AGENCY_OWNER, AgencyUser.ROLE_AGENCY_MANAGER])
    Notification.objects.bulk_create([
        Notification(
            agency=agency,
            user=user,
            title=("Listing reported by a visitor" if submission.kind == "listing_report" else f"New {submission.get_kind_display().lower()} submission"),
            message=submission.full_name or submission.email or "Website visitor",
            category="website_submission",
            link=(f"/inbox?lead={lead.id}" if lead else f"/website-submissions?submission={submission.id}"),
        )
        for user in recipients
    ])
    return Response(
        {"id": submission.id, "kind": submission.kind, "message": "Submission received successfully."},
        status=status.HTTP_201_CREATED,
    )


@extend_schema(request=PublicAgentReviewSerializer, responses={201: OpenApiTypes.OBJECT})
@api_view(["POST"])
@permission_classes([AllowAny])
@throttle_classes([PublicSubmissionRateThrottle])
def public_agent_review_create(request, slug, agent_id):
    agency = get_object_or_404(get_public_agencies_queryset(), slug=slug)
    agent = get_object_or_404(
        AgencyUser,
        id=agent_id,
        agency=agency,
        role=AgencyUser.ROLE_AGENT,
        is_active=True,
    )
    serializer = PublicAgentReviewSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    review = serializer.save(agency=agency, agent=agent)
    managers = AgencyUser.objects.filter(
        agency=agency,
        is_active=True,
        role__in=[AgencyUser.ROLE_AGENCY_OWNER, AgencyUser.ROLE_AGENCY_MANAGER],
    )
    Notification.objects.bulk_create([
        Notification(
            agency=agency,
            user=user,
            title="Agent review awaiting approval",
            message=f"{review.reviewer_name} reviewed {agent.full_name}",
            category="agent_review",
            link=f"/agent-reviews?review={review.id}",
        )
        for user in managers
    ])
    return Response(
        {"id": review.id, "message": "Review submitted for moderation."},
        status=status.HTTP_201_CREATED,
    )


@extend_schema(request=CustomerRegistrationSerializer, responses={201: CustomerProfileSerializer})
@api_view(["POST"])
@permission_classes([AllowAny])
@throttle_classes([PublicSubmissionRateThrottle])
def customer_register(request, slug):
    agency = get_object_or_404(get_public_agencies_queryset(), slug=slug)
    serializer = CustomerRegistrationSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    email = serializer.validated_data["email"].lower()
    if CustomerProfile.objects.filter(agency=agency, email__iexact=email).exists():
        raise ValidationError({"email": "A customer account already exists for this email."})
    customer = CustomerProfile(agency=agency, email=email, full_name=serializer.validated_data["full_name"], phone=serializer.validated_data.get("phone", ""))
    customer.set_password(serializer.validated_data["password"])
    customer.save()
    return Response({**CustomerProfileSerializer(customer).data, "access_token": customer.access_token}, status=status.HTTP_201_CREATED)


@extend_schema(request=CustomerLoginSerializer, responses=CustomerProfileSerializer)
@api_view(["POST"])
@permission_classes([AllowAny])
@throttle_classes([PublicSubmissionRateThrottle])
def customer_login(request, slug):
    agency = get_object_or_404(get_public_agencies_queryset(), slug=slug)
    serializer = CustomerLoginSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    customer = CustomerProfile.objects.filter(agency=agency, email__iexact=serializer.validated_data["email"]).first()
    if not customer or not customer.check_password(serializer.validated_data["password"]):
        return Response({"detail": "Invalid email or password."}, status=status.HTTP_400_BAD_REQUEST)
    customer.last_seen_at = timezone.now(); customer.save(update_fields=["last_seen_at", "updated_at"])
    return Response({**CustomerProfileSerializer(customer).data, "access_token": customer.access_token})


@extend_schema(request=SavedPropertySerializer, responses=SavedPropertySerializer(many=True))
@api_view(["GET", "POST"])
@permission_classes([AllowAny])
def customer_saved_properties(request, slug):
    agency = get_object_or_404(get_public_agencies_queryset(), slug=slug)
    customer = customer_from_request(request, agency)
    if request.method == "GET":
        return Response(SavedPropertySerializer(customer.saved_properties.select_related("property"), many=True).data)
    property_obj = get_object_or_404(Property, id=request.data.get("property"), agency=agency, is_published=True)
    saved, created = SavedProperty.objects.get_or_create(customer=customer, property=property_obj)
    if not created:
        saved.delete(); return Response(status=status.HTTP_204_NO_CONTENT)
    return Response(SavedPropertySerializer(saved).data, status=status.HTTP_201_CREATED)


@extend_schema(request=SavedSearchSerializer, responses=SavedSearchSerializer(many=True))
@api_view(["GET", "POST"])
@permission_classes([AllowAny])
def customer_saved_searches(request, slug):
    agency = get_object_or_404(get_public_agencies_queryset(), slug=slug)
    customer = customer_from_request(request, agency)
    if request.method == "GET":
        return Response(SavedSearchSerializer(customer.saved_searches.all(), many=True).data)
    serializer = SavedSearchSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    saved = serializer.save(agency=agency, customer=customer)
    return Response(SavedSearchSerializer(saved).data, status=status.HTTP_201_CREATED)


@extend_schema(request=AppointmentSerializer, responses=AppointmentSerializer(many=True))
@api_view(["GET", "POST"])
@permission_classes([AllowAny])
def public_appointments(request, slug):
    agency = get_object_or_404(get_public_agencies_queryset(), slug=slug)
    if request.method == "GET":
        slots = AppointmentAvailability.objects.filter(agency=agency, is_active=True).select_related("agent")
        return Response(AppointmentAvailabilitySerializer(slots, many=True).data)
    payload = request.data.copy()
    serializer = AppointmentSerializer(data=payload)
    serializer.is_valid(raise_exception=True)
    agent = serializer.validated_data.get("agent")
    property_obj = serializer.validated_data.get("property")
    if agent and agent.agency_id != agency.id:
        raise ValidationError({"agent": "Agent does not belong to this agency."})
    if property_obj and property_obj.agency_id != agency.id:
        raise ValidationError({"property": "Property does not belong to this agency."})
    customer = None
    if request.headers.get("X-Customer-Token"):
        customer = customer_from_request(request, agency)
    appointment = serializer.save(agency=agency, customer=customer)
    if appointment.agent:
        Notification.objects.create(agency=agency, user=appointment.agent, title="Appointment requested", message=f"{appointment.full_name} requested {appointment.starts_at:%Y-%m-%d %H:%M}", category="appointment", link="/appointments")
    return Response(AppointmentSerializer(appointment).data, status=status.HTTP_201_CREATED)


@extend_schema(responses=SubscriptionPlanSerializer(many=True))
@api_view(["GET"])
@permission_classes([AllowAny])
def subscription_plans(request):
    return Response(SubscriptionPlanSerializer(SubscriptionPlan.objects.filter(is_active=True), many=True).data)


def _stripe_signature_is_valid(request):
    secret = getattr(settings, "STRIPE_WEBHOOK_SECRET", "")
    signature = request.headers.get("Stripe-Signature", "")
    parts = dict(item.split("=", 1) for item in signature.split(",") if "=" in item)
    timestamp, provided = parts.get("t"), parts.get("v1")
    if not secret or not timestamp or not provided:
        return False
    try:
        if abs(timezone.now().timestamp() - int(timestamp)) > 300:
            return False
    except ValueError:
        return False
    payload = timestamp.encode() + b"." + request.body
    expected = hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, provided)


@extend_schema(request=OpenApiTypes.OBJECT, responses=OpenApiTypes.OBJECT)
@api_view(["POST"])
@permission_classes([AllowAny])
def stripe_webhook(request):
    if not _stripe_signature_is_valid(request):
        return Response({"detail": "Invalid signature."}, status=status.HTTP_400_BAD_REQUEST)
    try:
        event = json.loads(request.body)
    except json.JSONDecodeError:
        return Response({"detail": "Invalid payload."}, status=status.HTTP_400_BAD_REQUEST)
    event_type = event.get("type", "")
    obj = event.get("data", {}).get("object", {})
    metadata = obj.get("metadata", {}) or {}
    if event_type == "checkout.session.completed":
        agency = get_object_or_404(Agency, id=metadata.get("agency_id") or obj.get("client_reference_id"))
        plan = get_object_or_404(SubscriptionPlan, code=metadata.get("plan_code"))
        subscription, _ = Subscription.objects.update_or_create(
            agency=agency,
            defaults={"plan": plan, "status": "active", "provider_customer_id": obj.get("customer", ""), "provider_subscription_id": obj.get("subscription", "")},
        )
        agency.mark_paid()
    elif event_type in {"customer.subscription.updated", "customer.subscription.deleted"}:
        subscription = Subscription.objects.filter(provider_subscription_id=obj.get("id")).first()
        if subscription:
            mapped_status = "cancelled" if event_type.endswith("deleted") else obj.get("status", "active")
            if mapped_status not in dict(Subscription.STATUS_CHOICES):
                mapped_status = "past_due" if mapped_status in {"unpaid", "incomplete"} else "active"
            subscription.status = mapped_status
            subscription.cancel_at_period_end = obj.get("cancel_at_period_end", False)
            if obj.get("current_period_start"):
                subscription.current_period_start = datetime.fromtimestamp(obj["current_period_start"], tz=dt_timezone.utc)
            if obj.get("current_period_end"):
                subscription.current_period_end = datetime.fromtimestamp(obj["current_period_end"], tz=dt_timezone.utc)
                subscription.agency.subscription_expires_at = subscription.current_period_end
                subscription.agency.save(update_fields=["subscription_expires_at"])
            subscription.save()
    elif event_type == "invoice.paid":
        from .models import Payment
        subscription = Subscription.objects.filter(provider_subscription_id=obj.get("subscription")).first()
        if subscription:
            Payment.objects.update_or_create(
                provider_payment_id=obj.get("payment_intent") or obj.get("id", ""),
                defaults={"subscription": subscription, "amount": Decimal(obj.get("amount_paid", 0)) / 100, "currency": str(obj.get("currency", "usd")).upper(), "status": "paid", "receipt_url": obj.get("hosted_invoice_url", ""), "paid_at": timezone.now()},
            )
    return Response({"received": True})
