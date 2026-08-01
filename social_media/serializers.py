from rest_framework import serializers

from properties.models import Property
from .models import (
    SOCIAL_PUBLISH_PLATFORM_CHOICES,
    SocialPost,
    SocialPublishResult,
)


class SocialPublishResultSerializer(serializers.ModelSerializer):
    account_name = serializers.CharField(source="social_account.name", read_only=True)

    class Meta:
        model = SocialPublishResult
        fields = [
            "id",
            "social_account",
            "account_name",
            "platform",
            "status",
            "container_id",
            "external_post_id",
            "external_media_id",
            "error_message",
            "attempt_count",
            "published_at",
            "updated_at",
        ]


class SocialPostSerializer(serializers.ModelSerializer):
    property_title = serializers.SerializerMethodField()
    created_by_name = serializers.SerializerMethodField()
    publish_results = SocialPublishResultSerializer(many=True, read_only=True)
    target_platforms = serializers.ListField(
        child=serializers.ChoiceField(
            choices=SOCIAL_PUBLISH_PLATFORM_CHOICES
        ),
        required=False,
        allow_empty=True,
        help_text=(
            "Platforms to publish to. Use an array in JSON, or repeat the "
            "target_platforms form-data key for multipart requests."
        ),
    )

    class Meta:
        model = SocialPost
        fields = [
            "id",
            "agency",
            "property",
            "social_account",
            "property_title",
            "platform",
            "target_platforms",
            "caption",
            "image",
            "status",
            "scheduled_at",
            "published_at",
            "error_message",
            "external_post_id",
            "created_by",
            "created_by_name",
            "publish_results",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "agency",
            "created_by",
            "published_at",
            "error_message",
            "external_post_id",
        ]

    def get_property_title(self, obj) -> str | None:
        return obj.property.title if obj.property else None

    def get_created_by_name(self, obj) -> str | None:
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

    def validate_social_account(self, value):
        if value is None:
            return value
        request = self.context.get("request")
        if value.agency_id != request.user.agency_id:
            raise serializers.ValidationError(
                "You can only use a social account connected to your agency."
            )
        if value.status != value.STATUS_CONNECTED:
            raise serializers.ValidationError("The social account is not connected.")
        return value

    def validate_target_platforms(self, value):
        return list(dict.fromkeys(value))

    def validate(self, attrs):
        status_value = attrs.get(
            "status",
            self.instance.status if self.instance else SocialPost.STATUS_DRAFT,
        )
        scheduled_at = attrs.get(
            "scheduled_at",
            self.instance.scheduled_at if self.instance else None,
        )
        social_account = attrs.get(
            "social_account",
            self.instance.social_account if self.instance else None,
        )

        if status_value == SocialPost.STATUS_SCHEDULED:
            if scheduled_at is None:
                raise serializers.ValidationError(
                    {"scheduled_at": "Scheduled time is required."}
                )
            if social_account is None:
                raise serializers.ValidationError(
                    {"social_account": "A connected account is required."}
                )
        return attrs


class SocialPublishRequestSerializer(serializers.Serializer):
    platforms = serializers.ListField(
        child=serializers.ChoiceField(
            choices=SOCIAL_PUBLISH_PLATFORM_CHOICES
        ),
        required=False,
        allow_empty=False,
    )

    def validate_platforms(self, value):
        return list(dict.fromkeys(value))
    
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
            "webhook_subscription_status",
            "webhook_subscribed_at",
            "webhook_error",
            "created_at",
            "updated_at",
        ]
