from rest_framework import serializers
from django.core.exceptions import ObjectDoesNotExist
from django.utils import timezone
from datetime import timedelta

from leads.services import normalize_phone

from .models import Property, PropertyEvent, PropertyMedia
from .area import conversion_payload, price_per_area


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
    land_area_conversions = serializers.SerializerMethodField()
    price_per_aana = serializers.SerializerMethodField()
    price_per_dhur = serializers.SerializerMethodField()
    price_per_kattha = serializers.SerializerMethodField()
    price_per_land_sqft = serializers.SerializerMethodField()
    furnishing_status_display = serializers.SerializerMethodField()
    facing_direction_display = serializers.SerializerMethodField()
    verification_summary = serializers.SerializerMethodField()
    availability_status_display = serializers.CharField(source="get_status_display", read_only=True)
    freshness_state = serializers.SerializerMethodField()

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
            "price_per_aana", "price_per_dhur", "price_per_kattha", "price_per_land_sqft",

            "province",
            "district",
            "city",
            "neighbourhood",
            "municipality", "ward_number", "tole", "landmark",
            "address",
            "latitude",
            "longitude",
            "location_display",

            "bedrooms",
            "bathrooms",
            "floors",

            "land_area_value",
            "land_area_unit",
            "land_area_sqft", "land_area_conversions", "land_use_classification",
            "built_up_area_value",
            "built_up_area_unit",
            "road_access_value",
            "road_access_unit",
            "road_type", "mohada_value", "pichhad_value", "plot_dimension_unit", "plot_shape",
            "has_water_supply", "has_electricity", "has_drainage", "has_sewage",
            "major_road_type", "nearest_major_road", "major_road_distance_value", "major_road_distance_unit",

            "year_built",
            "parking_spaces",
            "parking_type",
            "furnishing_status",
            "furnishing_status_display",
            "facing_direction",
            "facing_direction_display",
            "verification_summary",

            "amenities",
            "virtual_tour_url",
            "video_tour_url",
            "short_description",
            "description",
            "seo_title",
            "seo_description",
            "share_slug",

            "is_featured",
            "status", "availability_status_display", "availability_verified_at",
            "listing_expires_at", "owner_confirmed_at", "freshness_state",
            "published_at",

            "agency_name",
            "assigned_agent_name",
            "assigned_agent_detail",

            "media",
            "created_at",
            "updated_at",
        ]

    def get_agency_name(self, obj) -> str | None:
        if obj.agency:
            return obj.agency.name

        return None

    def get_assigned_agent_name(self, obj) -> str | None:
        if obj.assigned_agent:
            return obj.assigned_agent.full_name

        return None

    def get_assigned_agent_detail(self, obj) -> dict | None:
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

    def get_location_display(self, obj) -> str:
        parts = [
            obj.tole or obj.neighbourhood,
            f"Ward {obj.ward_number}" if obj.ward_number else "",
            obj.municipality or obj.city,
            obj.district,
            obj.province,
        ]

        unique_parts = []
        seen = set()
        for part in parts:
            if part and str(part).casefold() not in seen:
                unique_parts.append(str(part))
                seen.add(str(part).casefold())
        return ", ".join(unique_parts)

    def get_display_property_id(self, obj) -> str:
        return f"LP-{obj.id:03d}"

    def get_price_per_sqft(self, obj) -> str | None:
        return price_per_area(obj.price, obj.built_up_area_value, obj.built_up_area_unit, "sqft")

    def get_land_area_conversions(self, obj): return conversion_payload(obj.land_area_value, obj.land_area_unit)
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

    def get_verification_summary(self, obj):
        try:
            verification = obj.verification
        except ObjectDoesNotExist:
            return {
                "level": "unverified", "label": "Not verified", "is_fully_verified": False,
                "completed_milestones": 0, "approved_documents": 0, "total_documents": 10,
            }
        documents = list(verification.documents.all())
        return {
            "level": verification.verification_level,
            "label": verification.verification_level_display,
            "is_fully_verified": verification.fully_verified,
            "completed_milestones": sum(
                bool(getattr(verification, field)) for field, _ in verification.MILESTONES
            ),
            "approved_documents": sum(
                document.status in {"approved", "not_applicable"} for document in documents
            ),
            "total_documents": 10,
        }

    def get_freshness_state(self, obj):
        if not obj.availability_verified_at or not obj.listing_expires_at:
            return "unconfirmed"
        if obj.listing_expires_at <= timezone.now():
            return "expired"
        if obj.listing_expires_at <= timezone.now() + timedelta(days=7):
            return "expiring_soon"
        return "fresh"


class PublicPropertyInquirySerializer(serializers.Serializer):
    full_name = serializers.CharField(max_length=255)
    phone = serializers.CharField(max_length=30)
    email = serializers.EmailField(required=False, allow_blank=True)
    message = serializers.CharField(required=False, allow_blank=True)

    def validate_full_name(self, value):
        return value.strip()

    def validate_phone(self, value):
        normalized = normalize_phone(value)
        if len(normalized.lstrip("+")) < 7:
            raise serializers.ValidationError("Enter a valid phone number.")
        return normalized

    def validate_email(self, value):
        return value.lower().strip()


class PublicPropertyEventSerializer(serializers.Serializer):
    event_type = serializers.ChoiceField(
        choices=[
            PropertyEvent.EVENT_VIEW,
            PropertyEvent.EVENT_WHATSAPP_CLICK,
            PropertyEvent.EVENT_VIBER_CLICK,
            PropertyEvent.EVENT_CALL_CLICK,
        ]
    )
    visitor_id = serializers.CharField(max_length=100, required=False, allow_blank=True)
    referrer = serializers.URLField(max_length=1000, required=False, allow_blank=True)
    utm_source = serializers.CharField(max_length=100, required=False, allow_blank=True)
    utm_medium = serializers.CharField(max_length=100, required=False, allow_blank=True)
    utm_campaign = serializers.CharField(max_length=150, required=False, allow_blank=True)
    metadata = serializers.JSONField(required=False)
