from rest_framework import serializers
from .models import Agency

class TestMarkAgencyPaidSerializer(serializers.Serializer):
    email = serializers.EmailField()
    license_number = serializers.CharField(max_length=100)
    verify_email = serializers.BooleanField(default=True)

class AgencySerializer(serializers.ModelSerializer):
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
        ]
