from rest_framework import serializers

from properties.models import Property
from .models import SocialPost


class SocialPostSerializer(serializers.ModelSerializer):
    property_title = serializers.SerializerMethodField()
    created_by_name = serializers.SerializerMethodField()

    class Meta:
        model = SocialPost
        fields = [
            "id",
            "agency",
            "property",
            "property_title",
            "platform",
            "caption",
            "image",
            "status",
            "scheduled_at",
            "published_at",
            "error_message",
            "created_by",
            "created_by_name",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "agency",
            "created_by",
            "published_at",
            "error_message",
        ]

    def get_property_title(self, obj):
        return obj.property.title if obj.property else None

    def get_created_by_name(self, obj):
        return obj.created_by.full_name if obj.created_by else None

    def validate_property(self, value):
        request = self.context.get("request")

        if not value:
            return value

        if value.agency != request.user.agency:
            raise serializers.ValidationError(
                "You can only create social posts for your own agency properties."
            )

        return value
    
from .models import SocialAccount


class SocialAccountSerializer(serializers.ModelSerializer):
    class Meta:
        model = SocialAccount
        fields = [
            "id",
            "provider",
            "platform",
            "external_id",
            "name",
            "username",
            "page_id",
            "status",
            "created_at",
            "updated_at",
        ]