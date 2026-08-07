from django.contrib.auth.password_validation import validate_password
from django.conf import settings
from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import serializers

from users.models import AgencyUser
from agencies.models import Agency
from .models import (
    Appointment, AppointmentAvailability, AuditLog, Contact, CustomerProfile,
    CustomFieldDefinition, Deal, Document, Invitation, Lease, Notification,
    AgentReview, Offer, Owner, Payment, PipelineStage, PublicSubmission,
    SavedProperty, SavedSearch, Subscription, SubscriptionPlan, Task,
)
from .validators import validate_custom_data


class AgencyValidationMixin:
    relation_fields = ()
    custom_module = None

    def validate(self, attrs):
        attrs = super().validate(attrs)
        request = self.context.get("request")
        agency = getattr(getattr(request, "user", None), "agency", None)
        if agency:
            for field in self.relation_fields:
                value = attrs.get(field)
                if value is not None and getattr(value, "agency_id", agency.id) != agency.id:
                    raise serializers.ValidationError({field: "This record must belong to your agency."})
            if self.custom_module:
                data = attrs.get("custom_data", getattr(self.instance, "custom_data", {}))
                validate_custom_data(agency, self.custom_module, data)
        return attrs


class ContactSerializer(AgencyValidationMixin, serializers.ModelSerializer):
    custom_module = "contact"
    assigned_to_name = serializers.CharField(source="assigned_to.full_name", read_only=True)
    relation_fields = ("lead", "assigned_to")

    class Meta:
        model = Contact
        exclude = ["agency"]
        read_only_fields = ["created_at", "updated_at"]


class OwnerSerializer(AgencyValidationMixin, serializers.ModelSerializer):
    custom_module = "owner"
    property_titles = serializers.SerializerMethodField()
    relation_fields = ("contact",)

    class Meta:
        model = Owner
        exclude = ["agency"]
        read_only_fields = ["created_at", "updated_at"]

    def get_property_titles(self, obj) -> list[str]:
        return [item.title for item in obj.properties.all()]

    def validate_properties(self, values):
        request = self.context.get("request")
        if request and any(item.agency_id != request.user.agency_id for item in values):
            raise serializers.ValidationError("All properties must belong to your agency.")
        return values


class DealSerializer(AgencyValidationMixin, serializers.ModelSerializer):
    custom_module = "deal"
    stage = serializers.CharField(max_length=30, required=False)
    assigned_agent_name = serializers.CharField(source="assigned_agent.full_name", read_only=True)
    lead_name = serializers.CharField(source="lead.full_name", read_only=True)
    contact_name = serializers.CharField(source="contact.full_name", read_only=True)
    property_title = serializers.CharField(source="property.title", read_only=True)
    offers_count = serializers.IntegerField(source="offers.count", read_only=True)
    relation_fields = ("lead", "contact", "property", "assigned_agent")

    class Meta:
        model = Deal
        exclude = ["agency"]
        read_only_fields = ["created_at", "updated_at", "closed_at"]

    def validate(self, attrs):
        attrs = super().validate(attrs)
        stage = attrs.get("stage", getattr(self.instance, "stage", "qualified"))
        request = self.context.get("request")
        allowed_stages = {choice[0] for choice in Deal.STAGES}
        if request and request.user.agency_id:
            allowed_stages.update(PipelineStage.objects.filter(agency=request.user.agency, module="deal").values_list("key", flat=True))
        if stage not in allowed_stages:
            raise serializers.ValidationError({"stage": "Unknown pipeline stage."})
        lost_reason = attrs.get("lost_reason", getattr(self.instance, "lost_reason", ""))
        if stage == "closed_lost" and not lost_reason.strip():
            raise serializers.ValidationError({"lost_reason": "A lost reason is required."})
        return attrs


class OfferSerializer(AgencyValidationMixin, serializers.ModelSerializer):
    deal_title = serializers.CharField(source="deal.title", read_only=True)
    submitted_by_name = serializers.CharField(source="submitted_by.full_name", read_only=True)
    relation_fields = ("deal",)

    class Meta:
        model = Offer
        exclude = ["agency"]
        read_only_fields = ["submitted_by", "responded_at", "created_at", "updated_at"]


class DocumentSerializer(AgencyValidationMixin, serializers.ModelSerializer):
    uploaded_by_name = serializers.CharField(source="uploaded_by.full_name", read_only=True)
    file_url = serializers.SerializerMethodField()
    relation_fields = ("property", "deal", "contact", "owner")

    class Meta:
        model = Document
        exclude = ["agency"]
        read_only_fields = ["uploaded_by", "created_at", "updated_at"]

    def get_file_url(self, obj) -> str | None:
        request = self.context.get("request")
        return request.build_absolute_uri(obj.file.url) if obj.file and request else (obj.file.url if obj.file else None)

    def validate_file(self, value):
        max_size = getattr(settings, "MAX_UPLOAD_SIZE_MB", 15) * 1024 * 1024
        if value.size > max_size:
            raise serializers.ValidationError("File is too large.")
        allowed = getattr(settings, "ALLOWED_MEDIA_CONTENT_TYPES", [])
        content_type = getattr(value, "content_type", "")
        if content_type and allowed and content_type not in allowed:
            raise serializers.ValidationError("Unsupported file type.")
        return value


class LeaseSerializer(AgencyValidationMixin, serializers.ModelSerializer):
    custom_module = "lease"
    property_title = serializers.CharField(source="property.title", read_only=True)
    tenant_name = serializers.CharField(source="tenant.full_name", read_only=True)
    owner_name = serializers.CharField(source="owner.full_name", read_only=True)
    assigned_agent_name = serializers.CharField(source="assigned_agent.full_name", read_only=True)
    relation_fields = ("property", "tenant", "owner", "assigned_agent")

    class Meta:
        model = Lease
        exclude = ["agency"]
        read_only_fields = ["created_at", "updated_at"]

    def validate(self, attrs):
        attrs = super().validate(attrs)
        start = attrs.get("start_date", getattr(self.instance, "start_date", None))
        end = attrs.get("end_date", getattr(self.instance, "end_date", None))
        if start and end and end <= start:
            raise serializers.ValidationError({"end_date": "End date must be after the start date."})
        day = attrs.get("payment_day", getattr(self.instance, "payment_day", 1))
        if not 1 <= day <= 28:
            raise serializers.ValidationError({"payment_day": "Payment day must be between 1 and 28."})
        return attrs


class TaskSerializer(AgencyValidationMixin, serializers.ModelSerializer):
    assigned_to_name = serializers.CharField(source="assigned_to.full_name", read_only=True)
    created_by_name = serializers.CharField(source="created_by.full_name", read_only=True)
    relation_fields = ("assigned_to", "lead", "deal", "property")

    class Meta:
        model = Task
        exclude = ["agency"]
        read_only_fields = ["created_by", "completed_at", "created_at", "updated_at"]


class NotificationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Notification
        exclude = ["agency", "user"]
        read_only_fields = ["title", "message", "category", "link", "created_at"]


class InvitationSerializer(serializers.ModelSerializer):
    invited_by_name = serializers.CharField(source="invited_by.full_name", read_only=True)

    class Meta:
        model = Invitation
        exclude = ["agency"]
        read_only_fields = ["invited_by", "expires_at", "accepted_at", "delivery_error", "created_at"]

    def validate_role(self, value):
        if value not in {AgencyUser.ROLE_AGENT, AgencyUser.ROLE_AGENCY_MANAGER}:
            raise serializers.ValidationError("Invite role must be agent or agency_manager.")
        return value


class InvitationAcceptSerializer(serializers.Serializer):
    token = serializers.UUIDField()
    password = serializers.CharField(write_only=True)

    def validate_password(self, value):
        try:
            validate_password(value)
        except DjangoValidationError as exc:
            raise serializers.ValidationError(list(exc.messages)) from exc
        return value


class TeamMemberSerializer(serializers.ModelSerializer):
    class Meta:
        model = AgencyUser
        fields = ["id", "full_name", "email", "phone", "role", "is_active", "created_at"]
        read_only_fields = ["id", "email", "created_at"]

    def validate_role(self, value):
        if value not in {
            AgencyUser.ROLE_AGENCY_OWNER,
            AgencyUser.ROLE_AGENCY_MANAGER,
            AgencyUser.ROLE_AGENT,
        }:
            raise serializers.ValidationError("Unsupported agency role.")
        return value


class PlatformAgencySerializer(serializers.ModelSerializer):
    users_count = serializers.IntegerField(source="users.count", read_only=True)
    properties_count = serializers.IntegerField(source="properties.count", read_only=True)

    class Meta:
        model = Agency
        fields = ["id", "name", "license_number", "slug", "email", "phone", "payment_status", "paid_at", "is_active", "subscription_expires_at", "users_count", "properties_count", "created_at"]
        read_only_fields = ["id", "license_number", "slug", "paid_at", "users_count", "properties_count", "created_at"]


class CustomFieldDefinitionSerializer(serializers.ModelSerializer):
    class Meta:
        model = CustomFieldDefinition
        exclude = ["agency"]
        read_only_fields = ["created_at", "updated_at"]


class PipelineStageSerializer(serializers.ModelSerializer):
    class Meta:
        model = PipelineStage
        exclude = ["agency"]
        read_only_fields = ["created_at", "updated_at"]


class AuditLogSerializer(serializers.ModelSerializer):
    actor_name = serializers.CharField(source="actor.full_name", read_only=True)

    class Meta:
        model = AuditLog
        fields = [
            "id", "actor", "actor_name", "action", "entity_type", "entity_id",
            "summary", "changes", "ip_address", "created_at",
        ]
        read_only_fields = fields


class CustomerProfileSerializer(serializers.ModelSerializer):
    class Meta:
        model = CustomerProfile
        exclude = ["agency", "access_token", "password_hash"]
        read_only_fields = ["created_at", "updated_at", "last_seen_at"]


class CustomerRegistrationSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True)

    class Meta:
        model = CustomerProfile
        fields = ["full_name", "email", "phone", "password"]

    def validate_password(self, value):
        try:
            validate_password(value)
        except DjangoValidationError as exc:
            raise serializers.ValidationError(list(exc.messages)) from exc
        return value


class CustomerLoginSerializer(serializers.Serializer):
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True)


class SavedPropertySerializer(serializers.ModelSerializer):
    property_title = serializers.CharField(source="property.title", read_only=True)
    property_price = serializers.DecimalField(source="property.price", max_digits=15, decimal_places=2, read_only=True)

    class Meta:
        model = SavedProperty
        fields = ["id", "property", "property_title", "property_price", "created_at"]
        read_only_fields = ["created_at"]


class SavedSearchSerializer(serializers.ModelSerializer):
    class Meta:
        model = SavedSearch
        exclude = ["agency", "customer"]
        read_only_fields = ["last_notified_at", "created_at", "updated_at"]


class PublicSubmissionSerializer(AgencyValidationMixin, serializers.ModelSerializer):
    property_title = serializers.CharField(source="property.title", read_only=True)
    agent_name = serializers.CharField(source="agent.full_name", read_only=True)
    lead_name = serializers.CharField(source="lead.full_name", read_only=True)
    relation_fields = ("property", "agent", "lead")

    class Meta:
        model = PublicSubmission
        exclude = ["agency"]
        read_only_fields = [
            "lead", "ip_address", "user_agent", "processed_at", "created_at", "updated_at",
        ]

    def validate(self, attrs):
        attrs = super().validate(attrs)
        kind = attrs.get("kind", getattr(self.instance, "kind", ""))
        full_name = (attrs.get("full_name") or "").strip()
        email = (attrs.get("email") or "").strip()
        phone = (attrs.get("phone") or "").strip()
        metadata = attrs.get("metadata") or {}

        errors = {}
        if kind not in {"newsletter", "listing_report"} and not full_name:
            errors["full_name"] = "Full name is required."
        if kind in {"newsletter", "buyer_guide", "career"} and not email:
            errors["email"] = "Email is required for this submission type."
        if kind in {"contact", "property_inquiry", "valuation", "demo"} and not (email or phone):
            errors["phone"] = "Provide at least a phone number or email address."
        if not isinstance(metadata, dict):
            errors["metadata"] = "Metadata must be an object."
        elif kind == "valuation" and not metadata.get("address"):
            errors["metadata"] = "A valuation request must include an address."
        if kind == "property_inquiry" and not attrs.get("property") and not (
            isinstance(metadata, dict) and metadata.get("property_title")
        ):
            errors["property"] = "Choose a property."
        if kind == "listing_report":
            if not attrs.get("property"):
                errors["property"] = "Choose the listing being reported."
            if not isinstance(metadata, dict) or not metadata.get("reason"):
                errors["metadata"] = "Choose a reason for reporting this listing."
        if errors:
            raise serializers.ValidationError(errors)
        return attrs


class AgentReviewSerializer(AgencyValidationMixin, serializers.ModelSerializer):
    agent_name = serializers.CharField(source="agent.full_name", read_only=True)
    approved_by_name = serializers.CharField(source="approved_by.full_name", read_only=True)
    relation_fields = ("agent",)

    class Meta:
        model = AgentReview
        exclude = ["agency"]
        read_only_fields = ["approved_by", "approved_at", "created_at", "updated_at"]


class PublicAgentReviewSerializer(serializers.ModelSerializer):
    class Meta:
        model = AgentReview
        fields = ["reviewer_name", "reviewer_email", "rating", "title", "comment"]


class AppointmentAvailabilitySerializer(AgencyValidationMixin, serializers.ModelSerializer):
    agent_name = serializers.CharField(source="agent.full_name", read_only=True)
    relation_fields = ("agent",)

    class Meta:
        model = AppointmentAvailability
        exclude = ["agency"]
        read_only_fields = ["created_at", "updated_at"]

    def validate_weekday(self, value):
        if value not in range(7):
            raise serializers.ValidationError("Weekday must be between 0 (Monday) and 6 (Sunday).")
        return value


class AppointmentSerializer(AgencyValidationMixin, serializers.ModelSerializer):
    agent_name = serializers.CharField(source="agent.full_name", read_only=True)
    property_title = serializers.CharField(source="property.title", read_only=True)
    relation_fields = ("agent", "property", "customer")

    class Meta:
        model = Appointment
        exclude = ["agency"]
        read_only_fields = ["created_at", "updated_at"]

    def validate(self, attrs):
        attrs = super().validate(attrs)
        start = attrs.get("starts_at", getattr(self.instance, "starts_at", None))
        end = attrs.get("ends_at", getattr(self.instance, "ends_at", None))
        if start and end and end <= start:
            raise serializers.ValidationError({"ends_at": "End time must be after start time."})
        return attrs


class SubscriptionPlanSerializer(serializers.ModelSerializer):
    class Meta:
        model = SubscriptionPlan
        fields = "__all__"


class PaymentSerializer(serializers.ModelSerializer):
    class Meta:
        model = Payment
        fields = "__all__"
        read_only_fields = ["subscription", "created_at"]


class SubscriptionSerializer(serializers.ModelSerializer):
    plan_details = SubscriptionPlanSerializer(source="plan", read_only=True)
    payments = PaymentSerializer(many=True, read_only=True)

    class Meta:
        model = Subscription
        exclude = ["agency"]
        read_only_fields = ["provider_customer_id", "provider_subscription_id", "current_period_start", "current_period_end", "created_at", "updated_at"]
