from datetime import datetime
import re

from django.contrib.auth.password_validation import validate_password
from django.conf import settings
from django.core.exceptions import ValidationError as DjangoValidationError
from django.utils import timezone
from rest_framework import serializers

from users.models import AgencyUser
from agencies.models import Agency
from .models import (
    Appointment, AppointmentAvailability, AuditLog, Contact, CustomerProfile,
    CustomFieldDefinition, Deal, Document, Invitation, Lease, Notification,
    AgentReview, Offer, Owner, Payment, PipelineStage, PublicSubmission,
    SavedProperty, SavedSearch, Subscription, SubscriptionPlan, Task,
)
from .validators import custom_field_in_use, validate_custom_data


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
    lead_name = serializers.CharField(source="lead.full_name", read_only=True)
    file_url = serializers.SerializerMethodField()
    relation_fields = ("lead", "property", "deal", "contact", "owner")

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
        read_only_fields = ["created_by", "completed_at", "generated_from", "created_at", "updated_at"]

    def validate(self, attrs):
        attrs = super().validate(attrs)
        recurrence = attrs.get("recurrence", getattr(self.instance, "recurrence", ""))
        due_at = attrs.get("due_at", getattr(self.instance, "due_at", None))
        if recurrence and not due_at:
            raise serializers.ValidationError({"due_at": "A due date is required for a recurring task."})
        return attrs


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

    def validate(self, attrs):
        request = self.context.get("request")
        agency = getattr(getattr(request, "user", None), "agency", None)
        module = attrs.get("module", getattr(self.instance, "module", None))
        key = attrs.get("key", getattr(self.instance, "key", None))
        field_type = attrs.get(
            "field_type", getattr(self.instance, "field_type", "text")
        )
        options = attrs.get("options", getattr(self.instance, "options", [])) or []
        if not isinstance(options, list) or any(
            not isinstance(item, str) or not item.strip() for item in options
        ):
            raise serializers.ValidationError({"options": "Options must be non-empty text values."})
        normalized = [item.strip() for item in options]
        if len({item.casefold() for item in normalized}) != len(normalized):
            raise serializers.ValidationError({"options": "Duplicate options are not allowed."})
        if field_type in {"select", "multiselect"} and not normalized:
            raise serializers.ValidationError({"options": "Select fields require at least one option."})
        if field_type not in {"select", "multiselect"} and normalized:
            raise serializers.ValidationError({"options": "Only select fields can define options."})
        attrs["options"] = normalized
        if agency and CustomFieldDefinition.objects.filter(
            agency=agency, module=module, key=key
        ).exclude(pk=getattr(self.instance, "pk", None)).exists():
            raise serializers.ValidationError({"key": "This key already exists in the selected module."})
        if self.instance:
            if module != self.instance.module or key != self.instance.key:
                raise serializers.ValidationError({"key": "Module and API key cannot be changed after creation."})
            if field_type != self.instance.field_type and custom_field_in_use(self.instance):
                raise serializers.ValidationError({
                    "field_type": "This field type cannot change while records contain values for it."
                })
        return attrs


class PipelineStageSerializer(serializers.ModelSerializer):
    class Meta:
        model = PipelineStage
        exclude = ["agency"]
        read_only_fields = ["created_at", "updated_at"]

    def validate(self, attrs):
        request = self.context.get("request")
        agency = getattr(getattr(request, "user", None), "agency", None)
        module = attrs.get("module", getattr(self.instance, "module", None))
        key = attrs.get("key", getattr(self.instance, "key", None))
        sort_order = attrs.get("sort_order", getattr(self.instance, "sort_order", 0))
        is_closed = attrs.get("is_closed", getattr(self.instance, "is_closed", False))
        is_won = attrs.get("is_won", getattr(self.instance, "is_won", False))
        if is_won and not is_closed:
            raise serializers.ValidationError({"is_closed": "A won stage must also be closed."})
        color = attrs.get("color", getattr(self.instance, "color", "#496B5A"))
        if not re.fullmatch(r"#[0-9A-Fa-f]{6}", color or ""):
            raise serializers.ValidationError({"color": "Enter a six-digit hex colour."})
        if agency:
            peers = PipelineStage.objects.filter(agency=agency, module=module)
            peers = peers.exclude(pk=getattr(self.instance, "pk", None))
            if peers.filter(key=key).exists():
                raise serializers.ValidationError({"key": "This stage key already exists in the pipeline."})
            if peers.filter(sort_order=sort_order).exists():
                raise serializers.ValidationError({"sort_order": "Each stage must have a unique order."})
            if is_won and peers.filter(is_won=True).exists():
                raise serializers.ValidationError({"is_won": "Only one custom won stage is allowed per pipeline."})
        if self.instance and (
            module != self.instance.module or key != self.instance.key
        ):
            raise serializers.ValidationError({"key": "Pipeline and stage key cannot be changed after creation."})
        return attrs


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
        read_only_fields = [
            "last_notified_at", "last_checked_at", "last_match_count",
            "last_check_error", "created_at", "updated_at",
        ]

    def validate_filters(self, value):
        if not isinstance(value, dict):
            raise serializers.ValidationError("Filters must be an object.")
        allowed = {"property_type", "purpose", "province", "district", "city", "location", "price_min", "price_max"}
        unknown = sorted(set(value) - allowed)
        if unknown:
            raise serializers.ValidationError(f"Unsupported filters: {', '.join(unknown)}.")
        normalized = {}
        for key, raw in value.items():
            if raw in (None, ""):
                continue
            if key in {"price_min", "price_max"}:
                try:
                    amount = float(raw)
                except (TypeError, ValueError):
                    raise serializers.ValidationError({key: "Enter a valid number."})
                if amount < 0:
                    raise serializers.ValidationError({key: "Price cannot be negative."})
                normalized[key] = amount
            else:
                normalized[key] = str(raw).strip()
        if normalized.get("price_min") is not None and normalized.get("price_max") is not None:
            if normalized["price_min"] > normalized["price_max"]:
                raise serializers.ValidationError("Minimum price cannot exceed maximum price.")
        return normalized

    def validate(self, attrs):
        attrs = super().validate(attrs)
        customer = self.context.get("customer")
        filters = attrs.get("filters", getattr(self.instance, "filters", {}))
        if customer:
            duplicates = customer.saved_searches.all()
            if self.instance:
                duplicates = duplicates.exclude(pk=self.instance.pk)
            if any(saved.filters == filters for saved in duplicates.only("filters")):
                raise serializers.ValidationError({"filters": "An equivalent saved search already exists."})
        return attrs


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

    def validate_agent(self, value):
        request = self.context.get("request")
        if value.role != AgencyUser.ROLE_AGENT or not value.is_active:
            raise serializers.ValidationError("Choose an active agent.")
        if request and request.user.is_authenticated:
            if request.user.role == AgencyUser.ROLE_AGENT and value.pk != request.user.pk:
                raise serializers.ValidationError("Agents can only manage their own availability.")
            if request.user.role != AgencyUser.ROLE_SUPER_ADMIN and value.agency_id != request.user.agency_id:
                raise serializers.ValidationError("Choose an agent from your agency.")
        return value

    def validate(self, attrs):
        attrs = super().validate(attrs)
        agent = attrs.get("agent", getattr(self.instance, "agent", None))
        weekday = attrs.get("weekday", getattr(self.instance, "weekday", None))
        start = attrs.get("start_time", getattr(self.instance, "start_time", None))
        end = attrs.get("end_time", getattr(self.instance, "end_time", None))
        slot_minutes = attrs.get("slot_minutes", getattr(self.instance, "slot_minutes", 30))

        errors = {}
        if start and end and end <= start:
            errors["end_time"] = "End time must be after start time."
        if slot_minutes < 10 or slot_minutes > 480:
            errors["slot_minutes"] = "Slot length must be between 10 and 480 minutes."
        if start and end:
            window_minutes = int(
                (datetime.combine(timezone.localdate(), end) - datetime.combine(timezone.localdate(), start)).total_seconds() // 60
            )
            if window_minutes > 0 and slot_minutes > window_minutes:
                errors["slot_minutes"] = "Slot length cannot exceed the availability window."
            elif window_minutes > 0 and window_minutes % slot_minutes != 0:
                errors["slot_minutes"] = "Availability window must divide evenly into appointment slots."
        if errors:
            raise serializers.ValidationError(errors)

        if agent and weekday is not None and start and end:
            overlapping = AppointmentAvailability.objects.filter(
                agent=agent,
                weekday=weekday,
                start_time__lt=end,
                end_time__gt=start,
            )
            if self.instance:
                overlapping = overlapping.exclude(pk=self.instance.pk)
            if overlapping.exists():
                raise serializers.ValidationError({"start_time": "This availability window overlaps an existing window."})
        return attrs


class AppointmentSerializer(AgencyValidationMixin, serializers.ModelSerializer):
    agent_name = serializers.CharField(source="agent.full_name", read_only=True)
    property_title = serializers.CharField(source="property.title", read_only=True)
    relation_fields = ("agent", "property", "customer")

    class Meta:
        model = Appointment
        exclude = ["agency"]
        read_only_fields = ["created_at", "updated_at"]
        extra_kwargs = {"agent": {"required": True, "allow_null": False}}

    def validate(self, attrs):
        attrs = super().validate(attrs)
        agent = attrs.get("agent", getattr(self.instance, "agent", None))
        start = attrs.get("starts_at", getattr(self.instance, "starts_at", None))
        end = attrs.get("ends_at", getattr(self.instance, "ends_at", None))
        if start and end and end <= start:
            raise serializers.ValidationError({"ends_at": "End time must be after start time."})

        request = self.context.get("request")
        if agent:
            if agent.role != AgencyUser.ROLE_AGENT or not agent.is_active:
                raise serializers.ValidationError({"agent": "Choose an active agent."})
            if request and request.user.is_authenticated:
                if request.user.role == AgencyUser.ROLE_AGENT and agent.pk != request.user.pk:
                    raise serializers.ValidationError({"agent": "Agents can only manage their own appointments."})
                if request.user.role != AgencyUser.ROLE_SUPER_ADMIN and agent.agency_id != request.user.agency_id:
                    raise serializers.ValidationError({"agent": "Choose an agent from your agency."})

        schedule_changed = self.instance is None or any(
            field in attrs for field in ("agent", "starts_at", "ends_at")
        )
        if not schedule_changed or not (agent and start and end):
            return attrs

        if start <= timezone.now():
            raise serializers.ValidationError({"starts_at": "Appointment time must be in the future."})

        local_start = timezone.localtime(start)
        local_end = timezone.localtime(end)
        if local_start.date() != local_end.date():
            raise serializers.ValidationError({"ends_at": "Appointment must start and end on the same day."})

        start_time = local_start.time().replace(tzinfo=None)
        end_time = local_end.time().replace(tzinfo=None)
        candidates = AppointmentAvailability.objects.filter(
            agency_id=agent.agency_id,
            agent=agent,
            weekday=local_start.weekday(),
            is_active=True,
            start_time__lte=start_time,
            end_time__gte=end_time,
        )
        matching_window = None
        duration_seconds = (end - start).total_seconds()
        for window in candidates:
            offset_seconds = (
                datetime.combine(local_start.date(), start_time) - datetime.combine(local_start.date(), window.start_time)
            ).total_seconds()
            if duration_seconds == window.slot_minutes * 60 and offset_seconds % (window.slot_minutes * 60) == 0:
                matching_window = window
                break
        if matching_window is None:
            raise serializers.ValidationError(
                {"starts_at": "Choose an available appointment slot with the configured slot length."}
            )

        agency_id = agent.agency_id
        conflicts = Appointment.objects.filter(
            agency_id=agency_id,
            agent=agent,
            starts_at__lt=end,
            ends_at__gt=start,
        ).exclude(status="cancelled")
        if self.instance:
            conflicts = conflicts.exclude(pk=self.instance.pk)
        if conflicts.exists():
            raise serializers.ValidationError({"starts_at": "This agent is already booked during that time."})

        email = attrs.get("email", getattr(self.instance, "email", ""))
        if email:
            duplicate = Appointment.objects.filter(
                agency_id=agency_id,
                email__iexact=email,
                starts_at__lt=end,
                ends_at__gt=start,
            ).exclude(status="cancelled")
            if self.instance:
                duplicate = duplicate.exclude(pk=self.instance.pk)
            if duplicate.exists():
                raise serializers.ValidationError({"starts_at": "This customer already has an appointment during that time."})
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
