from decimal import Decimal, ROUND_HALF_UP
from django.conf import settings

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

    def validate_file(self, value):
        if value is None:
            return value

        max_size_mb = getattr(settings, "MAX_UPLOAD_SIZE_MB", 15)
        if value.size > max_size_mb * 1024 * 1024:
            raise serializers.ValidationError(
                f"File size cannot exceed {max_size_mb} MB."
            )

        allowed_types = getattr(
            settings,
            "ALLOWED_MEDIA_CONTENT_TYPES",
            [
                "image/jpeg",
                "image/png",
                "image/webp",
                "application/pdf",
                "video/mp4",
            ],
        )
        content_type = getattr(value, "content_type", "")
        if content_type and content_type not in allowed_types:
            raise serializers.ValidationError("Unsupported file type.")
        return value

    def validate(self, attrs):
        file_value = attrs.get("file", getattr(self.instance, "file", None))
        external_url = attrs.get(
            "external_url",
            getattr(self.instance, "external_url", ""),
        )
        if not file_value and not external_url:
            raise serializers.ValidationError(
                "Provide either an uploaded file or an external URL."
            )
        return attrs

    def create(self, validated_data):
        instance = super().create(validated_data)
        if instance.is_primary:
            PropertyMedia.objects.filter(
                property=instance.property,
                is_primary=True,
            ).exclude(id=instance.id).update(is_primary=False)
        return instance

    def update(self, instance, validated_data):
        instance = super().update(instance, validated_data)
        if instance.is_primary:
            PropertyMedia.objects.filter(
                property=instance.property,
                is_primary=True,
            ).exclude(id=instance.id).update(is_primary=False)
        return instance


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

    def get_assigned_agent_name(self, obj) -> str | None:
        if obj.assigned_agent:
            return obj.assigned_agent.full_name

        return None

    def get_assigned_agent_detail(self, obj) -> dict | None:
        if not obj.assigned_agent:
            return None

        return {
            "id": obj.assigned_agent.id,
            "full_name": obj.assigned_agent.full_name,
            "email": obj.assigned_agent.email,
            "role": obj.assigned_agent.role,
        }

    def get_display_property_id(self, obj) -> str:
        return f"LP-{obj.id:03d}"

    def get_price_per_sqft(self, obj) -> str | None:
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

    def get_furnishing_status_display(self, obj) -> str | None:
        if not obj.furnishing_status:
            return None

        return obj.get_furnishing_status_display()

    def get_facing_direction_display(self, obj) -> str | None:
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

    def validate(self, attrs):
        status_value = attrs.get(
            "status",
            self.instance.status if self.instance else "draft",
        )
        is_published = attrs.get(
            "is_published",
            self.instance.is_published if self.instance else False,
        )

        if is_published and status_value != "available":
            raise serializers.ValidationError(
                {
                    "is_published": (
                        "Only properties with status='available' can be published. "
                        "Set status to 'available' in the same request."
                    )
                }
            )

        return attrs
