from rest_framework import serializers
from django.contrib.auth import get_user_model

from .models import Agency
from leads.services import normalize_phone

User = get_user_model()


class PublicAgencySerializer(serializers.ModelSerializer):
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
            "business_hours",
            "primary_color",

            "facebook_url",
            "instagram_url",
            "tiktok_url",
            "youtube_url",
            "linkedin_url",
            "whatsapp_number",
            "viber_number",
        ]


class PublicAgentSerializer(serializers.ModelSerializer):
    profile_image_url = serializers.SerializerMethodField()

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
            "bio",
        ]

    def get_profile_image_url(self, obj) -> str | None:
        if not obj.profile_image:
            return None

        request = self.context.get("request")
        if request:
            return request.build_absolute_uri(obj.profile_image.url)

        return obj.profile_image.url


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
