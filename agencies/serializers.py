from rest_framework import serializers
from django.conf import settings
from django.core import signing
from .models import Agency
from .localization import (
    format_nepal_address, format_nepal_phone, resolved_message_templates,
)
from .website_onboarding import validate_website_config, website_readiness

class TestMarkAgencyPaidSerializer(serializers.Serializer):
    email = serializers.EmailField()
    license_number = serializers.CharField(max_length=100)
    verify_email = serializers.BooleanField(default=True)

class AgencySerializer(serializers.ModelSerializer):
    resolved_message_templates = serializers.SerializerMethodField()
    address_display = serializers.SerializerMethodField()
    phone_display = serializers.SerializerMethodField()

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
            "website_template",
            "website_config",
            "website_draft_config",
            "website_onboarding_status",
            "website_onboarding_step",
            "website_onboarding_completed_at",
            "website_published_at",
            "default_language",
            "default_date_system",
            "use_nepali_digits",
            "timezone",
            "message_templates",
            "resolved_message_templates",
            "address_display",
            "phone_display",
            "is_website_published",
            "facebook_url",
            "instagram_url",
            "tiktok_url",
            "youtube_url",
            "linkedin_url",
            "whatsapp_number",
            "viber_number",
            "payment_status",
            "paid_at",
            "is_active",
            "subscription_expires_at",
            "created_at",
        ]
        read_only_fields = [
            "id",
            "license_number",
            "slug",
            "payment_status",
            "paid_at",
            "is_active",
            "subscription_expires_at",
            "created_at",
            "resolved_message_templates",
            "address_display",
            "phone_display",
            "is_website_published",
            "website_onboarding_status",
            "website_onboarding_step",
            "website_onboarding_completed_at",
            "website_published_at",
        ]

    def get_resolved_message_templates(self, obj) -> dict:
        return resolved_message_templates(obj.message_templates)

    def get_address_display(self, obj) -> str:
        return format_nepal_address(
            obj, language=obj.default_language,
            nepali_digits=obj.use_nepali_digits,
        )

    def get_phone_display(self, obj) -> str:
        return format_nepal_phone(
            obj.phone, nepali_digits=obj.use_nepali_digits
        ) if obj.phone else ""

    def validate_timezone(self, value):
        if value != "Asia/Kathmandu":
            raise serializers.ValidationError("Nexora currently uses Nepal time (Asia/Kathmandu).")
        return value


class WebsiteOnboardingSerializer(serializers.ModelSerializer):
    completion_percentage = serializers.SerializerMethodField()
    is_ready_to_publish = serializers.SerializerMethodField()
    missing_fields = serializers.SerializerMethodField()
    website_url = serializers.SerializerMethodField()
    preview_url = serializers.SerializerMethodField()

    class Meta:
        model = Agency
        fields = [
            "id",
            "name",
            "slug",
            "logo",
            "cover_image",
            "about",
            "email",
            "phone",
            "address",
            "province",
            "district",
            "municipality",
            "ward_number",
            "tole",
            "business_hours",
            "primary_color",
            "seo_title",
            "seo_description",
            "facebook_url",
            "instagram_url",
            "tiktok_url",
            "youtube_url",
            "linkedin_url",
            "whatsapp_number",
            "viber_number",
            "website_template",
            "website_draft_config",
            "website_onboarding_status",
            "website_onboarding_step",
            "website_onboarding_completed_at",
            "website_published_at",
            "is_website_published",
            "completion_percentage",
            "is_ready_to_publish",
            "missing_fields",
            "website_url",
            "preview_url",
        ]
        read_only_fields = [
            "id",
            "slug",
            "website_template",
            "website_onboarding_status",
            "website_onboarding_completed_at",
            "website_published_at",
            "is_website_published",
            "completion_percentage",
            "is_ready_to_publish",
            "missing_fields",
            "website_url",
            "preview_url",
        ]

    def validate_primary_color(self, value):
        value = value.strip().upper()
        if len(value) != 7 or not value.startswith("#"):
            raise serializers.ValidationError("Enter a six-digit hex colour such as #496B5A.")
        try:
            int(value[1:], 16)
        except ValueError:
            raise serializers.ValidationError("Enter a six-digit hex colour such as #496B5A.")
        return value

    def validate_website_onboarding_step(self, value):
        if value < 1 or value > 8:
            raise serializers.ValidationError("Onboarding step must be between 1 and 8.")
        return value

    def validate_website_draft_config(self, value):
        return validate_website_config(value)

    def validate_logo(self, value):
        return self._validate_image(value)

    def validate_cover_image(self, value):
        return self._validate_image(value)

    def _validate_image(self, value):
        if value.size > 5 * 1024 * 1024:
            raise serializers.ValidationError("Images must be 5 MB or smaller.")
        if value.content_type not in {"image/jpeg", "image/png", "image/webp"}:
            raise serializers.ValidationError("Upload a JPG, PNG, or WebP image.")
        return value

    def _readiness(self, obj):
        if not hasattr(obj, "_website_readiness"):
            obj._website_readiness = website_readiness(obj)
        return obj._website_readiness

    def get_completion_percentage(self, obj):
        return self._readiness(obj)["completion_percentage"]

    def get_is_ready_to_publish(self, obj):
        return self._readiness(obj)["is_ready_to_publish"]

    def get_missing_fields(self, obj):
        return self._readiness(obj)["missing_fields"]

    def get_website_url(self, obj):
        base = getattr(settings, "STOREFRONT_PUBLIC_URL", "http://localhost:3000").rstrip("/")
        return f"{base}/agency/{obj.slug}"

    def get_preview_url(self, obj):
        base = getattr(settings, "STOREFRONT_PUBLIC_URL", "http://localhost:3000").rstrip("/")
        token = signing.dumps({"agency_id": obj.id}, salt="agency-website-preview", compress=True)
        return f"{base}/website-preview/{token}"
