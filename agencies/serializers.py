from rest_framework import serializers

from .models import Agency


class TestMarkAgencyPaidSerializer(serializers.Serializer):
    email = serializers.EmailField()
    license_number = serializers.CharField(max_length=100)
    verify_email = serializers.BooleanField(default=True)


class AgencyProfileSerializer(serializers.ModelSerializer):
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
            "whatsapp_number",
            "payment_status",
            "paid_at",
            "created_at",
        ]
        read_only_fields = [
            "id",
            "license_number",
            "payment_status",
            "paid_at",
            "created_at",
        ]