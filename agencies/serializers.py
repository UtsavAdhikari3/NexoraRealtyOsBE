from urllib.parse import urljoin

from rest_framework import serializers
from django.conf import settings
from django.core import signing
from .models import Agency
from .localization import (
    format_nepal_address, format_nepal_phone, resolved_message_templates,
)
from .website_onboarding import (
    materialize_website_config,
    validate_website_config,
    website_readiness,
)

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
            "website_published_config",
            "website_onboarding_status",
            "website_onboarding_step",
            "website_completion_percentage",
            "website_config_version",
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
            "website_published_config",
            "website_draft_config",
            "website_completion_percentage",
            "website_config_version",
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

    def validate_website_config(self, value):
        return validate_website_config(value)


class WebsiteOnboardingSerializer(serializers.ModelSerializer):
    completion_percentage = serializers.SerializerMethodField()
    is_ready_to_publish = serializers.SerializerMethodField()
    missing_fields = serializers.SerializerMethodField()
    website_url = serializers.SerializerMethodField()
    preview_url = serializers.SerializerMethodField()
    media_urls = serializers.SerializerMethodField()

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
            "website_published_config",
            "website_onboarding_status",
            "website_onboarding_step",
            "website_completion_percentage",
            "website_config_version",
            "website_onboarding_completed_at",
            "website_published_at",
            "is_website_published",
            "completion_percentage",
            "is_ready_to_publish",
            "missing_fields",
            "website_url",
            "preview_url",
            "media_urls",
        ]
        read_only_fields = [
            "id",
            "slug",
            "website_template",
            "website_onboarding_status",
            "website_onboarding_completed_at",
            "website_published_at",
            "is_website_published",
            "website_published_config",
            "website_completion_percentage",
            "website_config_version",
            "completion_percentage",
            "is_ready_to_publish",
            "missing_fields",
            "website_url",
            "preview_url",
            "media_urls",
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
        if value < 1 or value > 9:
            raise serializers.ValidationError("Onboarding step must be between 1 and 9.")
        return value

    def validate_website_draft_config(self, value):
        cleaned = validate_website_config(value)
        if not self.instance:
            return cleaned
        if cleaned["featured_property_mode"] == "manual":
            from django.utils import timezone
            from properties.models import Property

            selected_ids = cleaned["featured_property_ids"]
            eligible_ids = set(Property.objects.filter(
                agency=self.instance,
                id__in=selected_ids,
                is_published=True,
                status__in=["available", "reserved", "under_negotiation"],
                requires_republish_approval=False,
                listing_expires_at__gt=timezone.now(),
            ).values_list("id", flat=True))
            invalid = [item for item in selected_ids if item not in eligible_ids]
            if invalid:
                raise serializers.ValidationError({
                    "featured_property_ids": "Only this agency's currently published, unexpired properties can be selected."
                })
        allowed = set()
        for source in [self.instance.website_draft_config, self.instance.website_published_config, self.instance.website_config]:
            for key, media_value in (source.get("media") or {}).items() if isinstance(source, dict) else []:
                allowed.update(media_value if key == "partner_logos" and isinstance(media_value, list) else [media_value])
        if self.instance.logo:
            allowed.add(self.instance.logo.name)
        if self.instance.cover_image:
            allowed.add(self.instance.cover_image.name)
        submitted = cleaned.get("media", {})
        paths = [value for key, media_value in submitted.items() for value in (media_value if key == "partner_logos" else [media_value]) if value]
        unknown = [path for path in paths if path not in allowed]
        if unknown:
            raise serializers.ValidationError("Website media must be uploaded through the agency media endpoint.")
        return cleaned

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

    def update(self, instance, validated_data):
        was_completed = instance.website_onboarding_status == Agency.WEBSITE_ONBOARDING_COMPLETED
        incoming_config = validated_data.pop("website_draft_config", instance.website_draft_config)
        instance = super().update(instance, validated_data)
        instance.website_draft_config = materialize_website_config(instance, incoming_config)
        readiness = website_readiness(instance, instance.website_draft_config)
        instance.website_completion_percentage = readiness["completion_percentage"]
        instance.website_onboarding_status = Agency.WEBSITE_ONBOARDING_COMPLETED if was_completed else (
            Agency.WEBSITE_ONBOARDING_READY if readiness["is_ready_to_publish"] else Agency.WEBSITE_ONBOARDING_IN_PROGRESS
        )
        instance.save(update_fields=[
            "website_draft_config", "website_completion_percentage", "website_onboarding_status",
        ])
        instance._website_readiness = readiness
        return instance

    def to_representation(self, instance):
        data = super().to_representation(instance)
        data["website_draft_config"] = materialize_website_config(instance)
        return data

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

    def get_media_urls(self, obj):
        from django.core.files.storage import default_storage
        media = materialize_website_config(obj).get("media", {})
        request = self.context.get("request")
        def resolve(value):
            if not value:
                return None
            if value.startswith(("http://", "https://")):
                return value
            url = default_storage.url(value)
            public_api_base = getattr(settings, "PUBLIC_API_BASE_URL", "").strip()
            if public_api_base:
                return urljoin(f"{public_api_base.rstrip('/')}/", url.lstrip("/"))
            return request.build_absolute_uri(url) if request else url
        return {
            key: ([resolve(item) for item in value] if key == "partner_logos" else resolve(value))
            for key, value in media.items()
        }
