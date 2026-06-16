from django.contrib.auth import get_user_model
from rest_framework import serializers

User = get_user_model()


class RegisterSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, min_length=8)

    class Meta:
        model = User
        fields = ["id", "email", "password", "agency_name", "agency_license_number"]

    def validate_email(self, value):
        email = value.lower().strip()

        if User.objects.filter(email=email).exists():
            raise serializers.ValidationError("An agency with this email already exists.")

        return email

    def validate_agency_license_number(self, value):
        license_number = value.strip()

        if User.objects.filter(agency_license_number=license_number).exists():
            raise serializers.ValidationError("An agency with this license number already exists.")

        return license_number

    def create(self, validated_data):
        return User.objects.create_user(**validated_data)