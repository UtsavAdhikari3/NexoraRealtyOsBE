from rest_framework import serializers
from .models import Agency
from .localization import (
    format_nepal_address, format_nepal_phone, resolved_message_templates,
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
