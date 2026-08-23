import json

from rest_framework import serializers
from django.core.exceptions import ObjectDoesNotExist
from django.utils import timezone
from datetime import timedelta

from agencies.serializer_fields import NepalPhoneField

from .models import Property, PropertyEvent, PropertyMedia
from .area import conversion_payload, price_per_area


class PublicPropertyMediaSerializer(serializers.ModelSerializer):
    original = serializers.SerializerMethodField()
    card = serializers.SerializerMethodField()
    large = serializers.SerializerMethodField()

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
            "alt_text",
            "sort_order",
            "is_primary",
            "created_at",
            "original",
            "card",
            "large",
        ]

    def _payload(self, obj, field_name, width_name, height_name):
        field = getattr(obj, field_name, None)
        if not field:
            return None
        request = self.context.get("request")
        url = field.url
        if request and not url.startswith(("http://", "https://")):
            url = request.build_absolute_uri(url)
        return {
            "url": url,
            "width": getattr(obj, width_name, None),
            "height": getattr(obj, height_name, None),
        }

    def get_original(self, obj):
        payload = self._payload(obj, "file", "original_width", "original_height")
        if payload:
            return payload
        if obj.external_url:
            return {"url": obj.external_url, "width": None, "height": None}
        return None

    def get_card(self, obj):
        return self._payload(obj, "card_image", "card_width", "card_height") or self.get_original(obj)

    def get_large(self, obj):
        return self._payload(obj, "large_image", "large_width", "large_height") or self.get_original(obj)


class PublicPropertyCardSerializer(serializers.ModelSerializer):
    display_property_id = serializers.SerializerMethodField()
    location_display = serializers.SerializerMethodField()
    area = serializers.SerializerMethodField()
    primary_image = serializers.SerializerMethodField()
    assigned_agent = serializers.SerializerMethodField()
    freshness_state = serializers.SerializerMethodField()
    verification = serializers.SerializerMethodField()
    latitude = serializers.SerializerMethodField()
    longitude = serializers.SerializerMethodField()
    tole = serializers.SerializerMethodField()
    neighbourhood = serializers.SerializerMethodField()
    image_count = serializers.SerializerMethodField()
    video_count = serializers.SerializerMethodField()

    class Meta:
        model = Property
        fields = [
            "id", "display_property_id", "share_slug", "title", "property_type",
            "purpose", "status", "price", "currency", "rent_period", "province", "district",
            "city", "municipality", "neighbourhood", "tole", "location_display",
            "latitude", "longitude",
            "bedrooms", "bathrooms", "area", "is_featured", "published_at",
            "freshness_state", "verification", "primary_image", "image_count",
            "video_count", "assigned_agent",
        ]

    def _public_media(self, obj):
        media_items = getattr(obj, "_ordered_public_media", None)
        return media_items if media_items is not None else list(obj.media.filter(is_public=True))

    def get_image_count(self, obj):
        return sum(item.media_type == "image" for item in self._public_media(obj))

    def get_video_count(self, obj):
        return sum(item.media_type in {"video", "reel"} for item in self._public_media(obj))

    def get_display_property_id(self, obj):
        return f"LP-{obj.id:03d}"

    def get_location_display(self, obj):
        parts = [obj.municipality or obj.city, obj.district, obj.province]
        if obj.show_exact_location_publicly:
            parts.insert(0, obj.tole or obj.neighbourhood)
        seen = set()
        output = []
        for value in parts:
            key = str(value or "").strip().casefold()
            if key and key not in seen:
                seen.add(key)
                output.append(str(value).strip())
        return ", ".join(output)

    def get_latitude(self, obj):
        return obj.latitude if obj.show_exact_location_publicly else None

    def get_longitude(self, obj):
        return obj.longitude if obj.show_exact_location_publicly else None

    def get_tole(self, obj):
        return obj.tole if obj.show_exact_location_publicly else ""

    def get_neighbourhood(self, obj):
        return obj.neighbourhood if obj.show_exact_location_publicly else ""

    def get_area(self, obj):
        if obj.land_area_value is not None and obj.land_area_unit:
            return {"value": str(obj.land_area_value), "unit": obj.land_area_unit, "kind": "land"}
        if obj.built_up_area_value is not None and obj.built_up_area_unit:
            return {"value": str(obj.built_up_area_value), "unit": obj.built_up_area_unit, "kind": "built_up"}
        return None

    def get_primary_image(self, obj):
        media_items = self._public_media(obj)
        image = next((item for item in media_items if item.media_type == "image"), None)
        if not image:
            return None
        request = self.context.get("request")
        source = image.card_image or image.thumbnail or image.file
        url = source.url if source else image.external_url
        if url and request and not url.startswith(("http://", "https://")):
            url = request.build_absolute_uri(url)
        return {
            "id": image.id,
            "url": url,
            "width": image.card_width or image.original_width,
            "height": image.card_height or image.original_height,
            "alt_text": image.alt_text or image.title or obj.title,
        }

    def get_assigned_agent(self, obj):
        if not obj.assigned_agent:
            return None
        return {"id": obj.assigned_agent_id, "name": obj.assigned_agent.full_name}

    def get_freshness_state(self, obj):
        if not obj.listing_expires_at:
            return "unconfirmed"
        if obj.listing_expires_at <= timezone.now() + timedelta(days=7):
            return "expiring_soon"
        return "fresh"

    def get_verification(self, obj):
        try:
            verification = obj.verification
        except ObjectDoesNotExist:
            return {"level": "unverified", "label": "Not verified"}
        return {
            "level": verification.verification_level,
            "label": verification.verification_level_display,
        }


class PublicPropertySerializer(serializers.ModelSerializer):
    media = PublicPropertyMediaSerializer(
        source="_ordered_public_media",
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
    address = serializers.SerializerMethodField()
    landmark = serializers.SerializerMethodField()
    tole = serializers.SerializerMethodField()
    neighbourhood = serializers.SerializerMethodField()
    ward_number = serializers.SerializerMethodField()
    latitude = serializers.SerializerMethodField()
    longitude = serializers.SerializerMethodField()
    canonical_url = serializers.SerializerMethodField()

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
            "rent_period",
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
            "canonical_url",

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

    def get_canonical_url(self, obj):
        from agencies.website_urls import property_website_url
        return property_website_url(obj)

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
            "email": obj.assigned_agent.email if obj.assigned_agent.show_email_publicly else None,
            "phone": obj.assigned_agent.phone if obj.assigned_agent.show_phone_publicly else None,
            "designation": obj.assigned_agent.designation,
            "bio": obj.assigned_agent.bio,
            "profile_image": profile_image_url,
        }

    def get_location_display(self, obj) -> str:
        parts = [obj.municipality or obj.city, obj.district, obj.province]
        if obj.show_exact_location_publicly:
            parts = [obj.tole or obj.neighbourhood, f"Ward {obj.ward_number}" if obj.ward_number else "", *parts]

        unique_parts = []
        seen = set()
        for part in parts:
            if part and str(part).casefold() not in seen:
                unique_parts.append(str(part))
                seen.add(str(part).casefold())
        return ", ".join(unique_parts)

    def get_address(self, obj):
        return obj.address if obj.show_exact_location_publicly else ""

    def get_landmark(self, obj):
        return obj.landmark if obj.show_exact_location_publicly else ""

    def get_tole(self, obj):
        return obj.tole if obj.show_exact_location_publicly else ""

    def get_neighbourhood(self, obj):
        return obj.neighbourhood if obj.show_exact_location_publicly else ""

    def get_ward_number(self, obj):
        return obj.ward_number if obj.show_exact_location_publicly else ""

    def get_latitude(self, obj):
        return obj.latitude if obj.show_exact_location_publicly else None

    def get_longitude(self, obj):
        return obj.longitude if obj.show_exact_location_publicly else None

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
    phone = NepalPhoneField()
    email = serializers.EmailField(required=False, allow_blank=True)
    message = serializers.CharField(required=False, allow_blank=True)
    utm_source = serializers.CharField(max_length=100, required=False, allow_blank=True)
    utm_medium = serializers.CharField(max_length=100, required=False, allow_blank=True)
    utm_campaign = serializers.CharField(max_length=150, required=False, allow_blank=True)
    distribution_code = serializers.CharField(max_length=16, required=False, allow_blank=True)

    def validate_full_name(self, value):
        return value.strip()

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

    def validate_metadata(self, value):
        if not isinstance(value, dict):
            raise serializers.ValidationError("Metadata must be an object.")
        if len(json.dumps(value, ensure_ascii=False, default=str).encode("utf-8")) > 2048:
            raise serializers.ValidationError("Metadata must be 2 KB or smaller.")
        return value
