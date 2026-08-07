from django.conf import settings

from rest_framework import serializers

from .models import Property, PropertyMedia
from .area import conversion_payload, price_per_area


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
    land_area_conversions = serializers.SerializerMethodField()
    price_per_aana = serializers.SerializerMethodField()
    price_per_dhur = serializers.SerializerMethodField()
    price_per_kattha = serializers.SerializerMethodField()
    price_per_land_sqft = serializers.SerializerMethodField()
    furnishing_status_display = serializers.SerializerMethodField()
    facing_direction_display = serializers.SerializerMethodField()

    class Meta:
        model = Property
        fields = "__all__"
        read_only_fields = (
            "agency",
            "share_slug",
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
        return price_per_area(obj.price, obj.built_up_area_value, obj.built_up_area_unit, "sqft")

    def get_land_area_conversions(self, obj):
        return conversion_payload(obj.land_area_value, obj.land_area_unit)

    def get_price_per_aana(self, obj): return price_per_area(obj.price, obj.land_area_value, obj.land_area_unit, "aana")
    def get_price_per_dhur(self, obj): return price_per_area(obj.price, obj.land_area_value, obj.land_area_unit, "dhur")
    def get_price_per_kattha(self, obj): return price_per_area(obj.price, obj.land_area_value, obj.land_area_unit, "kattha")
    def get_price_per_land_sqft(self, obj): return price_per_area(obj.price, obj.land_area_value, obj.land_area_unit, "sqft")

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
        def current(name, default=None):
            return attrs.get(name, getattr(self.instance, name, default) if self.instance else default)

        for value_field, unit_field in (
            ("land_area_value", "land_area_unit"), ("built_up_area_value", "built_up_area_unit"),
            ("road_access_value", "road_access_unit"),
            ("major_road_distance_value", "major_road_distance_unit"),
        ):
            value, unit = current(value_field), current(unit_field)
            if value is not None and value <= 0:
                raise serializers.ValidationError({value_field: "Must be greater than zero."})
            if value is not None and not unit:
                raise serializers.ValidationError({unit_field: "Select a unit."})
        for field in ("mohada_value", "pichhad_value"):
            if current(field) is not None and current(field) <= 0:
                raise serializers.ValidationError({field: "Must be greater than zero."})
        ward = str(current("ward_number", "")).strip()
        if ward and (not ward.isdigit() or int(ward) < 1 or int(ward) > 99):
            raise serializers.ValidationError({"ward_number": "Enter a ward number from 1 to 99."})

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

        request = self.context.get("request")
        if request and request.user.agency_id:
            from operations.validators import validate_custom_data
            validate_custom_data(
                request.user.agency,
                "property",
                attrs.get("custom_data", getattr(self.instance, "custom_data", {})),
            )

        return attrs
