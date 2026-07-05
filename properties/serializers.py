from decimal import Decimal, ROUND_HALF_UP

from rest_framework import serializers

from .models import Property, PropertyMedia


class PropertyMediaSerializer(serializers.ModelSerializer):
    class Meta:
        model = PropertyMedia
        fields = [
            "id",
            "property",
            "media_type",
            "file",
            "external_url",
            "thumbnail",
            "title",
            "caption",
            "sort_order",
            "is_primary",
            "uploaded_by",
            "created_at",
        ]

        read_only_fields = [
            "id",
            "property",
            "uploaded_by",
            "created_at",
        ]


class PropertySerializer(serializers.ModelSerializer):
    media = PropertyMediaSerializer(many=True, read_only=True)

    assigned_agent_name = serializers.SerializerMethodField()
    assigned_agent_detail = serializers.SerializerMethodField()

    display_property_id = serializers.SerializerMethodField()
    price_per_sqft = serializers.SerializerMethodField()
    furnishing_status_display = serializers.SerializerMethodField()
    facing_direction_display = serializers.SerializerMethodField()

    class Meta:
        model = Property
        fields = "__all__"
        read_only_fields = (
            "agency",
        )

    def get_assigned_agent_name(self, obj):
        if obj.assigned_agent:
            return obj.assigned_agent.full_name

        return None

    def get_assigned_agent_detail(self, obj):
        if not obj.assigned_agent:
            return None

        return {
            "id": obj.assigned_agent.id,
            "full_name": obj.assigned_agent.full_name,
            "email": obj.assigned_agent.email,
            "role": obj.assigned_agent.role,
        }

    def get_display_property_id(self, obj):
        return f"LP-{obj.id:03d}"

    def get_price_per_sqft(self, obj):
        if not obj.price:
            return None

        if not obj.built_up_area_value:
            return None

        area = Decimal(str(obj.built_up_area_value))

        if area <= 0:
            return None

        price = Decimal(str(obj.price))

        price_per_sqft = price / area

        price_per_sqft = price_per_sqft.quantize(
            Decimal("0.01"),
            rounding=ROUND_HALF_UP
        )

        return str(price_per_sqft)

    def get_furnishing_status_display(self, obj):
        if not obj.furnishing_status:
            return None

        return obj.get_furnishing_status_display()

    def get_facing_direction_display(self, obj):
        if not obj.facing_direction:
            return None

        return obj.get_facing_direction_display()

    def validate_assigned_agent(self, value):
        request = self.context["request"]

        if value is None:
            return value

        if value.agency != request.user.agency:
            raise serializers.ValidationError(
                "Assigned agent must belong to your agency."
            )

        if value.role != "agent":
            raise serializers.ValidationError(
                "Assigned user must be an agent."
            )

        return value