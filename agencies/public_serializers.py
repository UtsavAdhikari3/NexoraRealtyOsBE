from rest_framework import serializers

from .models import Agency


class PublicAgencySerializer(serializers.ModelSerializer):
    class Meta:
        model = Agency
        fields = [
            "id",
            "name",
            "license_number",
            "email",
            "phone",

            "facebook_url",
            "instagram_url",
            "tiktok_url",
            "youtube_url",
            "linkedin_url",
            "whatsapp_number",
            "viber_number",
        ]