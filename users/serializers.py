from django.contrib.auth import get_user_model
from django.db import transaction
from rest_framework import serializers

from agencies.models import Agency

User = get_user_model()


def normalize_string_list(values):
    normalized = []
    seen = set()
    for value in values:
        cleaned = value.strip()
        key = cleaned.casefold()
        if cleaned and key not in seen:
            normalized.append(cleaned)
            seen.add(key)
    return normalized


class AgentProfileMetricsMixin:
    def get_assigned_profile_properties(self, obj):
        if not hasattr(obj, "_agent_profile_properties"):
            obj._agent_profile_properties = list(obj.assigned_properties.all())
        return obj._agent_profile_properties

    def get_deals_closed(self, obj) -> int:
        return sum(
            property_obj.status in ["sold", "rented"]
            for property_obj in self.get_assigned_profile_properties(obj)
        )

    def get_current_listing_ids(self, obj) -> list[str]:
        property_ids = sorted(
            property_obj.id
            for property_obj in self.get_assigned_profile_properties(obj)
            if property_obj.status == "available" and property_obj.is_published
        )
        return [f"LP-{property_id:03d}" for property_id in property_ids]

    def get_sold_property_ids(self, obj) -> list[str]:
        property_ids = sorted(
            property_obj.id
            for property_obj in self.get_assigned_profile_properties(obj)
            if property_obj.status in ["sold", "rented"]
        )
        return [f"LP-{property_id:03d}" for property_id in property_ids]


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

from .models import AgencyUser
class AgentSerializer(serializers.ModelSerializer):
    class Meta:
        model = AgencyUser
        fields = [
            "id",
            "email",
            "full_name",
            "role",
            "phone",
            "profile_image",
            "designation",
            "bio",
            "is_active",
            "created_at",
        ]

        read_only_fields = [
            "id",
            "role",
            "created_at",
        ]


class AgentSelfProfileSerializer(AgentProfileMetricsMixin, serializers.ModelSerializer):
    profile_image_url = serializers.SerializerMethodField()
    profile_completed = serializers.BooleanField(
        source="agent_profile_completed",
        read_only=True,
    )
    deals_closed = serializers.SerializerMethodField()
    current_listing_ids = serializers.SerializerMethodField()
    sold_property_ids = serializers.SerializerMethodField()
    languages = serializers.ListField(
        child=serializers.CharField(max_length=100),
        required=False,
    )
    specialties = serializers.ListField(
        child=serializers.CharField(max_length=150),
        required=False,
    )

    class Meta:
        model = AgencyUser
        fields = [
            "id",
            "full_name",
            "email",
            "role",
            "phone",
            "profile_image",
            "profile_image_url",
            "designation",
            "location",
            "years_experience",
            "languages",
            "specialties",
            "bio",
            "linkedin_url",
            "instagram_url",
            "facebook_url",
            "deals_closed",
            "current_listing_ids",
            "sold_property_ids",
            "profile_completed",
            "profile_updated_at",
        ]
        read_only_fields = [
            "id",
            "email",
            "role",
            "deals_closed",
            "current_listing_ids",
            "sold_property_ids",
            "profile_completed",
            "profile_updated_at",
        ]

    def get_profile_image_url(self, obj) -> str | None:
        if not obj.profile_image:
            return None
        request = self.context.get("request")
        if request:
            return request.build_absolute_uri(obj.profile_image.url)
        return obj.profile_image.url

    def validate_languages(self, value):
        return normalize_string_list(value)

    def validate_specialties(self, value):
        return normalize_string_list(value)

    def validate_years_experience(self, value):
        if value > 80:
            raise serializers.ValidationError("Years of experience cannot exceed 80.")
        return value

class AgentCreateSerializer(serializers.Serializer):
    full_name = serializers.CharField(max_length=255)
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True, min_length=8)

    def validate_email(self, value):
        value = value.lower().strip()

        if User.objects.filter(email=value).exists():
            raise serializers.ValidationError(
                "User with this email already exists."
            )

        return value

    def create(self, validated_data):
        request = self.context["request"]

        if not request.user.agency_id:
            raise serializers.ValidationError(
                "Only agency users can create agents."
            )

        return User.objects.create_user(
            email=validated_data["email"],
            password=validated_data["password"],
            full_name=validated_data["full_name"],
            agency=request.user.agency,
            role="agent",
        )

    def to_representation(self, instance):
        return AgentSerializer(instance).data
    
class VerifyLoginOTPSerializer(serializers.Serializer):
    email = serializers.EmailField()
    otp = serializers.CharField(
        min_length=6,
        max_length=6
    )

    def validate_email(self, value):
        return value.lower().strip()


class ResendLoginOTPSerializer(serializers.Serializer):
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True)

    def validate_email(self, value):
        return value.lower().strip()
