from django.contrib.auth import get_user_model
from django.db import transaction
from rest_framework import serializers

from agencies.models import Agency

User = get_user_model()


class RegisterSerializer(serializers.Serializer):
    full_name = serializers.CharField(max_length=255)
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True, min_length=8)

    agency_name = serializers.CharField(max_length=255)
    license_number = serializers.CharField(max_length=100)

    def validate_email(self, value):
        value = value.lower().strip()

        if User.objects.filter(email=value).exists():
            raise serializers.ValidationError(
                "User with this email already exists."
            )

        return value

    def validate_license_number(self, value):
        value = value.strip()

        if Agency.objects.filter(
            license_number=value
        ).exists():
            raise serializers.ValidationError(
                "Agency with this license number already exists."
            )

        return value

    @transaction.atomic
    def create(self, validated_data):
        agency = Agency.objects.create(
            name=validated_data["agency_name"],
            license_number=validated_data["license_number"],
        )

        user = User.objects.create_user(
            email=validated_data["email"],
            password=validated_data["password"],
            full_name=validated_data["full_name"],
            agency=agency,
            role="agency_owner",
        )

        return user
    



class LoginResponseSerializer(serializers.Serializer):
    message = serializers.CharField()

    access = serializers.CharField()
    refresh = serializers.CharField()

    user = serializers.DictField()
    agency = serializers.DictField()