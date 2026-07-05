from decimal import Decimal, ROUND_HALF_UP

from rest_framework import serializers

from .models import Property, PropertyMedia


class PublicPropertyMediaSerializer(serializers.ModelSerializer):
    class Meta:
        model = PropertyMedia
        fields = [
            "id",
            "media_type",
            "file",
            "external_url",
            "thumbnail",
            "title",
            "caption",
            "sort_order",
            "is_primary",
            "created_at",
        ]


class PublicPropertySerializer(serializers.ModelSerializer):
    media = PublicPropertyMediaSerializer(
        many=True,
        read_only=True
    )

    agency_name = serializers.SerializerMethodField()
    assigned_agent_name = serializers.SerializerMethodField()
    assigned_agent_detail = serializers.SerializerMethodField()
    location_display = serializers.SerializerMethodField()

    display_property_id = serializers.SerializerMethodField()
    price_per_sqft = serializers.SerializerMethodField()
    furnishing_status_display = serializers.SerializerMethodField()
    facing_direction_display = serializers.SerializerMethodField()

    class Meta:
        model = Property
        fields = [
            "id",
            "display_property_id",

            "title",
            "property_type",
            "purpose",
            "price",
            "currency",
            "price_per_sqft",

            "province",
            "district",
            "city",
            "neighbourhood",
            "address",
            "latitude",
            "longitude",
            "location_display",

            "bedrooms",
            "bathrooms",
            "floors",

            "land_area_value",
            "land_area_unit",
            "built_up_area_value",
            "built_up_area_unit",
            "road_access_value",
            "road_access_unit",

            "year_built",
            "parking_spaces",
            "parking_type",
            "furnishing_status",
            "furnishing_status_display",
            "facing_direction",
            "facing_direction_display",

            "amenities",
            "virtual_tour_url",
            "short_description",
            "description",

            "is_featured",
            "published_at",

            "agency_name",
            "assigned_agent_name",
            "assigned_agent_detail",

            "media",
            "created_at",
            "updated_at",
        ]

    def get_agency_name(self, obj):
        if obj.agency:
            return obj.agency.name

        return None

    def get_assigned_agent_name(self, obj):
        if obj.assigned_agent:
            return obj.assigned_agent.full_name

        return None

    def get_assigned_agent_detail(self, obj):
        if not obj.assigned_agent:
            return None

        request = self.context.get("request")
        profile_image_url = None

        if obj.assigned_agent.profile_image:
            profile_image_url = obj.assigned_agent.profile_image.url

            if request:
                profile_image_url = request.build_absolute_uri(
                    obj.assigned_agent.profile_image.url
                )

        return {
            "id": obj.assigned_agent.id,
            "full_name": obj.assigned_agent.full_name,
            "email": obj.assigned_agent.email,
            "phone": obj.assigned_agent.phone,
            "designation": obj.assigned_agent.designation,
            "bio": obj.assigned_agent.bio,
            "profile_image": profile_image_url,
        }

    def get_location_display(self, obj):
        parts = [
            obj.neighbourhood,
            obj.city,
            obj.district,
            obj.province,
        ]

        return ", ".join(
            [
                part
                for part in parts
                if part
            ]
        )

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


class PublicPropertyInquirySerializer(serializers.Serializer):
    full_name = serializers.CharField(max_length=255)
    phone = serializers.CharField(max_length=30)
    email = serializers.EmailField(required=False, allow_blank=True)
    message = serializers.CharField(required=False, allow_blank=True)

    def validate_full_name(self, value):
        return value.strip()

    def validate_phone(self, value):
        return value.strip()

    def validate_email(self, value):
        return value.lower().strip()