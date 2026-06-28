from rest_framework import serializers

from .models import SiteVisit


class SiteVisitSerializer(serializers.ModelSerializer):
    lead_name = serializers.SerializerMethodField()
    property_title = serializers.SerializerMethodField()
    property_location = serializers.SerializerMethodField()
    assigned_agent_name = serializers.SerializerMethodField()
    created_by_name = serializers.SerializerMethodField()

    class Meta:
        model = SiteVisit
        fields = [
            "id",
            "agency",
            "lead",
            "lead_name",
            "property",
            "property_title",
            "property_location",
            "assigned_agent",
            "assigned_agent_name",
            "scheduled_at",
            "status",
            "notes",
            "created_by",
            "created_by_name",
            "created_at",
            "updated_at",
            "scheduled_email_sent_at",
            "scheduled_email_error",
        ]

        read_only_fields = [
            "id",
            "agency",
            "lead_name",
            "property_title",
            "property_location",
            "assigned_agent_name",
            "created_by",
            "created_by_name",
            "created_at",
            "updated_at",
        ]

    def get_lead_name(self, obj):
        return obj.lead.full_name

    def get_property_title(self, obj):
        return obj.property.title

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

    def get_assigned_agent_name(self, obj):
        if obj.assigned_agent:
            return obj.assigned_agent.full_name

        return None

    def get_created_by_name(self, obj):
        if obj.created_by:
            return obj.created_by.full_name

        return None

    def validate_lead(self, value):
        request = self.context.get("request")

        if request and value.agency != request.user.agency:
            raise serializers.ValidationError(
                "Lead must belong to your agency."
            )

        if request and request.user.role == "agent":
            if value.assigned_agent_id != request.user.id:
                raise serializers.ValidationError(
                    "Agents can only schedule site visits for their assigned leads."
                )

        return value

    def validate_property(self, value):
        request = self.context.get("request")

        if request and value.agency != request.user.agency:
            raise serializers.ValidationError(
                "Property must belong to your agency."
            )

        return value

    def validate_assigned_agent(self, value):
        if value is None:
            return value

        request = self.context.get("request")

        if request and request.user.role == "agent":
            raise serializers.ValidationError(
                "Agents cannot assign site visits to another agent."
            )

        if request and value.agency != request.user.agency:
            raise serializers.ValidationError(
                "Assigned agent must belong to your agency."
            )

        if value.role != "agent":
            raise serializers.ValidationError(
                "Assigned user must be an agent."
            )

        return value

    def validate(self, attrs):
        request = self.context.get("request")

        lead = attrs.get(
            "lead",
            self.instance.lead if self.instance else None
        )

        property_obj = attrs.get(
            "property",
            self.instance.property if self.instance else None
        )

        if lead and property_obj:
            if lead.agency_id != property_obj.agency_id:
                raise serializers.ValidationError(
                    "Lead and property must belong to the same agency."
                )

        if request and request.user.role == "agent":
            blocked_update_fields = {
                "lead",
                "property",
                "assigned_agent",
            }

            if self.instance:
                blocked_fields = blocked_update_fields.intersection(
                    set(self.initial_data.keys())
                )

                if blocked_fields:
                    raise serializers.ValidationError(
                        f"Agents cannot update these fields: {', '.join(sorted(blocked_fields))}"
                    )

        return attrs


class PublicSiteVisitRequestSerializer(serializers.Serializer):
    full_name = serializers.CharField(max_length=255)
    phone = serializers.CharField(max_length=30)
    email = serializers.EmailField(required=False, allow_blank=True)

    preferred_datetime = serializers.DateTimeField()

    message = serializers.CharField(
        required=False,
        allow_blank=True,
        style={
            "base_template": "textarea.html"
        }
    )