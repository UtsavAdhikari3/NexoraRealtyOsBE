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
        ]