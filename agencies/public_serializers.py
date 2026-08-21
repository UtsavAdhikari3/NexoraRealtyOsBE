from copy import deepcopy
from urllib.parse import urljoin

from rest_framework import serializers
from django.contrib.auth import get_user_model
from django.conf import settings

from .models import Agency
from leads.services import normalize_phone
from .localization import format_nepal_address, format_nepal_phone
from .website_onboarding import default_website_config
from .website_urls import agency_website_url

User = get_user_model()


class PublicAgencySerializer(serializers.ModelSerializer):
    address_display = serializers.SerializerMethodField()
    phone_display = serializers.SerializerMethodField()
    logo = serializers.SerializerMethodField()
    cover_image = serializers.SerializerMethodField()
    about = serializers.SerializerMethodField()
    email = serializers.SerializerMethodField()
    phone = serializers.SerializerMethodField()
    address = serializers.SerializerMethodField()
    business_hours = serializers.SerializerMethodField()
    primary_color = serializers.SerializerMethodField()
    seo_title = serializers.SerializerMethodField()
    seo_description = serializers.SerializerMethodField()
    website_config = serializers.SerializerMethodField()
    facebook_url = serializers.SerializerMethodField()
    instagram_url = serializers.SerializerMethodField()
    tiktok_url = serializers.SerializerMethodField()
    youtube_url = serializers.SerializerMethodField()
    linkedin_url = serializers.SerializerMethodField()
    whatsapp_number = serializers.SerializerMethodField()
    viber_number = serializers.SerializerMethodField()
    default_language = serializers.SerializerMethodField()
    website_config_version = serializers.IntegerField(read_only=True)
    custom_domain = serializers.SerializerMethodField()
    canonical_base_url = serializers.SerializerMethodField()

    class Meta:
        model = Agency
        fields = [
            "id",
            "name",
            "license_number",
            "slug",
            "logo",
            "cover_image",
            "about",
            "email",
            "phone",
            "address",
            "province",
            "district",
            "city",
            "municipality",
            "ward_number",
            "tole",
            "business_hours",
            "primary_color",
            "seo_title",
            "seo_description",
            "custom_domain",
            "canonical_base_url",
            "website_template",
            "website_config",
            "website_config_version",
            "is_website_published",
            "default_language",
            "default_date_system",
            "use_nepali_digits",
            "timezone",
            "address_display",
            "phone_display",

            "facebook_url",
            "instagram_url",
            "tiktok_url",
            "youtube_url",
            "linkedin_url",
            "whatsapp_number",
            "viber_number",
        ]

    def _config(self, obj):
        # Normal public requests must never fall back to the draft.
        return obj.website_published_config or obj.website_config or default_website_config()

    def get_custom_domain(self, obj):
        primary = obj.website_domains.filter(
            status="verified", is_active=True, is_primary=True
        ).only("domain").first()
        return primary.domain if primary else ""

    def get_canonical_base_url(self, obj):
        return agency_website_url(obj)

    def _media_url(self, value):
        if not value:
            return None
        if value.startswith(("https://", "http://")):
            return value
        from django.core.files.storage import default_storage
        url = default_storage.url(value)
        public_api_base = getattr(settings, "PUBLIC_API_BASE_URL", "").strip()
        if public_api_base:
            return urljoin(f"{public_api_base.rstrip('/')}/", url.lstrip("/"))
        request = self.context.get("request")
        return request.build_absolute_uri(url) if request else url

    def get_website_config(self, obj):
        config = deepcopy(self._config(obj))
        media = dict(config.get("media") or {})
        for key, value in list(media.items()):
            if key == "partner_logos":
                media[key] = [self._media_url(item) for item in value if item]
            else:
                media[key] = self._media_url(value)
        config["media"] = media
        return config

    def get_logo(self, obj):
        return self._media_url((self._config(obj).get("media") or {}).get("logo"))

    def get_cover_image(self, obj):
        return self._media_url((self._config(obj).get("media") or {}).get("hero_image"))

    def get_about(self, obj): return self._config(obj).get("about", "")
    def get_email(self, obj): return self._config(obj).get("public_email", "") or None
    def get_phone(self, obj): return self._config(obj).get("public_phone", "") or None
    def get_address(self, obj): return self._config(obj).get("address", "")
    def get_business_hours(self, obj): return self._config(obj).get("business_hours", "")
    def get_primary_color(self, obj): return self._config(obj).get("primary_color", "#496B5A")
    def get_seo_title(self, obj): return self._config(obj).get("seo_title", "")
    def get_seo_description(self, obj): return self._config(obj).get("seo_description", "")
    def get_facebook_url(self, obj): return self._config(obj).get("facebook_url", "") or None
    def get_instagram_url(self, obj): return self._config(obj).get("instagram_url", "") or None
    def get_tiktok_url(self, obj): return self._config(obj).get("tiktok_url", "") or None
    def get_youtube_url(self, obj): return self._config(obj).get("youtube_url", "") or None
    def get_linkedin_url(self, obj): return self._config(obj).get("linkedin_url", "") or None
    def get_whatsapp_number(self, obj): return self._config(obj).get("whatsapp_number", "") or None
    def get_viber_number(self, obj): return self._config(obj).get("viber_number", "") or None
    def get_default_language(self, obj): return self._config(obj).get("language", obj.default_language)

    def get_address_display(self, obj) -> str:
        return self.get_address(obj)

    def get_phone_display(self, obj) -> str:
        phone = self.get_phone(obj)
        return format_nepal_phone(phone, nepali_digits=obj.use_nepali_digits) if phone else ""


class PublicAgentSerializer(serializers.ModelSerializer):
    phone = serializers.SerializerMethodField()
    email = serializers.SerializerMethodField()
    profile_image_url = serializers.SerializerMethodField()
    profile_completed = serializers.BooleanField(
        source="agent_profile_completed",
        read_only=True,
    )
    deals_closed = serializers.SerializerMethodField()
    current_listing_ids = serializers.SerializerMethodField()
    sold_property_ids = serializers.SerializerMethodField()
    rating = serializers.SerializerMethodField()
    reviews = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = [
            "id",
            "full_name",
            "phone",
            "email",
            "profile_image",
            "profile_image_url",
            "designation",
            "location",
            "years_experience",
            "languages",
            "specialties",
            "bio",
            "linkedin_url",
            "instagram_url",
            "facebook_url",
            "deals_closed",
            "current_listing_ids",
            "sold_property_ids",
            "profile_completed",
            "rating",
            "reviews",
        ]

    def get_profile_image_url(self, obj) -> str | None:
        if not obj.profile_image:
            return None

        public_api_base = getattr(settings, "PUBLIC_API_BASE_URL", "").strip()
        if public_api_base:
            return urljoin(
                f"{public_api_base.rstrip('/')}/",
                obj.profile_image.url.lstrip("/"),
            )
        request = self.context.get("request")
        if request:
            return request.build_absolute_uri(obj.profile_image.url)

        return obj.profile_image.url

    def get_phone(self, obj):
        return obj.phone if obj.show_phone_publicly else None

    def get_email(self, obj):
        return obj.email if obj.show_email_publicly else None

    def get_assigned_profile_properties(self, obj):
        if not hasattr(obj, "_agent_profile_properties"):
            obj._agent_profile_properties = list(obj.assigned_properties.all())
        return obj._agent_profile_properties

    def get_deals_closed(self, obj) -> int:
        return sum(
            property_obj.status in ["sold", "rented"]
            for property_obj in self.get_assigned_profile_properties(obj)
        )

    def get_current_listing_ids(self, obj) -> list[str]:
        property_ids = sorted(
            property_obj.id
            for property_obj in self.get_assigned_profile_properties(obj)
            if property_obj.status == "available" and property_obj.is_published
        )
        return [f"LP-{property_id:03d}" for property_id in property_ids]

    def get_sold_property_ids(self, obj) -> list[str]:
        property_ids = sorted(
            property_obj.id
            for property_obj in self.get_assigned_profile_properties(obj)
            if property_obj.status in ["sold", "rented"]
        )
        return [f"LP-{property_id:03d}" for property_id in property_ids]

    def get_approved_reviews(self, obj):
        if not hasattr(obj, "_approved_public_reviews"):
            obj._approved_public_reviews = list(
                obj.public_reviews.filter(is_approved=True).order_by("-created_at")
            )
        return obj._approved_public_reviews

    def get_rating(self, obj) -> float:
        reviews = self.get_approved_reviews(obj)
        if not reviews:
            return 0
        return round(sum(review.rating for review in reviews) / len(reviews), 1)

    def get_reviews(self, obj) -> list[dict]:
        return [
            {
                "id": review.id,
                "name": review.reviewer_name,
                "rating": review.rating,
                "title": review.title,
                "comment": review.comment,
                "created_at": review.created_at,
            }
            for review in self.get_approved_reviews(obj)
        ]


class PublicAgencyContactSerializer(serializers.Serializer):
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
