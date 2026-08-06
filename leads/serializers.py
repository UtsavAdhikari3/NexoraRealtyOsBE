from rest_framework import serializers

from .models import Lead, LeadPropertyInterest, LeadInteraction, LeadStatusHistory


class LeadStatusHistorySerializer(serializers.ModelSerializer):
    changed_by_name = serializers.SerializerMethodField()

    class Meta:
        model = LeadStatusHistory
        fields = [
            "id",
            "from_status",
            "to_status",
            "changed_by",
            "changed_by_name",
            "note",
            "created_at",
        ]

    def get_changed_by_name(self, obj) -> str | None:
        return obj.changed_by.full_name if obj.changed_by else None


class LeadSerializer(serializers.ModelSerializer):
    status = serializers.CharField(max_length=40, required=False)
    assigned_agent_name = serializers.SerializerMethodField()
    property_interests_count = serializers.SerializerMethodField()
    interactions_count = serializers.SerializerMethodField()

    class Meta:
        model = Lead
        fields = [
            "id",
            "agency",
            "assigned_agent",
            "assigned_agent_name",
            "created_by",
            "full_name",
            "phone",
            "email",
            "source",
            "status",
            "budget_min",
            "budget_max",
            "preferred_location",
            "purpose",
            "property_type",
            "notes",
            "custom_data",
            "last_contacted_at",
            "next_follow_up_at",
            "follow_up_status",
            "lost_reason",
            "follow_up_reminder_sent_at",
            "follow_up_reminder_error",
            "property_interests_count",
            "interactions_count",
            "created_at",
            "updated_at",
        ]

        read_only_fields = [
            "id",
            "agency",
            "created_by",
            "assigned_agent_name",
            "property_interests_count",
            "interactions_count",
            "follow_up_status",
            "follow_up_reminder_sent_at",
            "follow_up_reminder_error",
            "created_at",
            "updated_at",
        ]

    def get_assigned_agent_name(self, obj) -> str | None:
        if obj.assigned_agent:
            return obj.assigned_agent.full_name

        return None

    def get_property_interests_count(self, obj) -> int:
        return obj.property_interests.count()

    def get_interactions_count(self, obj) -> int:
        return obj.interactions.count()

    def validate_assigned_agent(self, value):
        if value is None:
            return value

        request = self.context.get("request")
        
        if request and request.user.role == "agent":
            raise serializers.ValidationError(
                "Agents cannot assign or reassign leads."
            )

        if request and value.agency != request.user.agency:
            raise serializers.ValidationError(
                "Assigned agent must belong to your agency."
            )

        if value.role != "agent":
            raise serializers.ValidationError(
                "Assigned user must have role='agent'."
            )

        return value

    def validate(self, attrs):
        budget_min = attrs.get("budget_min")
        budget_max = attrs.get("budget_max")

        if budget_min is not None and budget_max is not None:
            if budget_min > budget_max:
                raise serializers.ValidationError(
                    {
                        "budget_max": "Budget max must be greater than or equal to budget min."
                    }
                )

        status_value = attrs.get(
            "status",
            self.instance.status if self.instance else Lead._meta.get_field("status").default,
        )
        request = self.context.get("request")
        allowed_statuses = {choice[0] for choice in Lead.STATUS_CHOICES}
        if request and request.user.agency_id:
            from operations.models import PipelineStage
            allowed_statuses.update(
                PipelineStage.objects.filter(
                    agency=request.user.agency,
                    module="lead",
                ).values_list("key", flat=True)
            )
        if status_value not in allowed_statuses:
            raise serializers.ValidationError({"status": "Unknown pipeline stage."})
        if request and request.user.agency_id:
            from operations.validators import validate_custom_data
            validate_custom_data(
                request.user.agency,
                "lead",
                attrs.get("custom_data", getattr(self.instance, "custom_data", {})),
            )
        lost_reason = attrs.get(
            "lost_reason",
            self.instance.lost_reason if self.instance else "",
        )

        if status_value == "lost" and not lost_reason.strip():
            raise serializers.ValidationError(
                {"lost_reason": "Lost reason is required when a lead is marked lost."}
            )

        next_follow_up_at = attrs.get("next_follow_up_at")
        if next_follow_up_at is not None:
            attrs["follow_up_status"] = Lead.FOLLOW_UP_PENDING

        return attrs


class LeadPropertyInterestSerializer(serializers.ModelSerializer):
    property_title = serializers.SerializerMethodField()
    property_price = serializers.SerializerMethodField()
    property_location = serializers.SerializerMethodField()

    class Meta:
        model = LeadPropertyInterest
        fields = [
            "id",
            "agency",
            "property",
            "property_title",
            "property_price",
            "property_location",
            "interest_level",
            "notes",
            "created_at",
        ]

        read_only_fields = [
            "id",
            "agency",
            "property_title",
            "property_price",
            "property_location",
            "created_at",
        ]

    def get_property_title(self, obj) -> str:
        return obj.property.title

    def get_property_price(self, obj) -> str:
        return obj.property.price

    def get_property_location(self, obj) -> str:
        parts = [
            obj.property.neighbourhood,
            obj.property.city,
            obj.property.district,
            obj.property.province,
        ]

        return ", ".join(
            [
                part
                for part in parts
                if part
            ]
        )

    def validate_property(self, value):
        request = self.context.get("request")

        if request and value.agency != request.user.agency:
            raise serializers.ValidationError(
                "Property must belong to your agency."
            )

        return value

    def validate(self, attrs):
        lead = self.context.get("lead")

        if not lead and self.instance:
            lead = self.instance.lead

        property_obj = attrs.get("property")

        if lead and property_obj:
            already_exists = LeadPropertyInterest.objects.filter(
                lead=lead,
                property=property_obj
            )

            if self.instance:
                already_exists = already_exists.exclude(
                    id=self.instance.id
                )

            if already_exists.exists():
                raise serializers.ValidationError(
                    "This property is already linked to this lead."
                )

        return attrs


class LeadInteractionSerializer(serializers.ModelSerializer):
    agent_name = serializers.SerializerMethodField()

    class Meta:
        model = LeadInteraction
        fields = [
            "id",
            "agency",
            "agent",
            "agent_name",
            "interaction_type",
            "note",
            "follow_up_date",
            "created_at",
        ]

        read_only_fields = [
            "id",
            "agency",
            "agent",
            "agent_name",
            "created_at",
        ]

    def get_agent_name(self, obj) -> str | None:
        if obj.agent:
            return obj.agent.full_name

        return None
