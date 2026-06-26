from rest_framework import serializers

from .models import Lead, LeadPropertyInterest, LeadInteraction


class LeadSerializer(serializers.ModelSerializer):
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
            "property_interests_count",
            "interactions_count",
            "created_at",
            "updated_at",
        ]

        read_only_fields = [
            "id",
            "agency",
            "assigned_agent_name",
            "property_interests_count",
            "interactions_count",
            "created_at",
            "updated_at",
        ]

    def get_assigned_agent_name(self, obj):
        if obj.assigned_agent:
            return obj.assigned_agent.full_name

        return None

    def get_property_interests_count(self, obj):
        return obj.property_interests.count()

    def get_interactions_count(self, obj):
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

    def get_property_title(self, obj):
        return obj.property.title

    def get_property_price(self, obj):
        return obj.property.price

    def get_property_location(self, obj):
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

    def get_agent_name(self, obj):
        if obj.agent:
            return obj.agent.full_name

        return None