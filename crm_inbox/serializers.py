from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework import serializers

from leads.models import Lead
from leads.services import normalize_phone

from .models import Conversation, SocialContact, SocialMessage

User = get_user_model()


class SocialContactSerializer(serializers.ModelSerializer):
    class Meta:
        model = SocialContact
        fields = [
            "id",
            "platform",
            "external_user_id",
            "display_name",
            "username",
            "profile_image_url",
            "linked_lead",
            "first_seen_at",
            "last_seen_at",
        ]


class SocialMessageSerializer(serializers.ModelSerializer):
    class Meta:
        model = SocialMessage
        fields = [
            "id",
            "provider_message_id",
            "direction",
            "message_type",
            "sender_external_id",
            "text",
            "attachments",
            "delivery_status",
            "error_message",
            "sent_at",
            "created_at",
        ]


class ConversationSerializer(serializers.ModelSerializer):
    contact = SocialContactSerializer(read_only=True)
    account_name = serializers.CharField(source="social_account.name", read_only=True)
    assigned_agent_name = serializers.CharField(
        source="assigned_agent.full_name",
        read_only=True,
    )
    linked_lead_name = serializers.CharField(source="linked_lead.full_name", read_only=True)

    class Meta:
        model = Conversation
        fields = [
            "id",
            "platform",
            "social_account",
            "account_name",
            "contact",
            "external_conversation_id",
            "assigned_agent",
            "assigned_agent_name",
            "linked_lead",
            "linked_lead_name",
            "status",
            "unread_count",
            "last_message_at",
            "last_message_preview",
            "created_at",
            "updated_at",
        ]


class ReplySerializer(serializers.Serializer):
    text = serializers.CharField(max_length=2000)

    def validate_text(self, value):
        value = value.strip()
        if not value:
            raise serializers.ValidationError("Message cannot be empty.")
        return value


class AssignConversationSerializer(serializers.Serializer):
    assigned_agent = serializers.PrimaryKeyRelatedField(
        queryset=User.objects.all(),
        allow_null=True,
    )

    def validate_assigned_agent(self, value):
        if value is None:
            return value
        conversation = self.context["conversation"]
        if value.agency_id != conversation.agency_id or value.role != User.ROLE_AGENT:
            raise serializers.ValidationError("Select an active agent from this agency.")
        if not value.is_active:
            raise serializers.ValidationError("The selected agent is inactive.")
        return value


class LinkLeadSerializer(serializers.Serializer):
    lead = serializers.PrimaryKeyRelatedField(queryset=Lead.objects.all())

    def validate_lead(self, value):
        conversation = self.context["conversation"]
        if value.agency_id != conversation.agency_id:
            raise serializers.ValidationError("Lead must belong to this agency.")
        return value


class CreateLeadFromConversationSerializer(serializers.Serializer):
    full_name = serializers.CharField(max_length=255)
    phone = serializers.CharField(max_length=30)
    email = serializers.EmailField(required=False, allow_blank=True)

    def validate_phone(self, value):
        normalized = normalize_phone(value)
        if len(normalized.lstrip("+")) < 7:
            raise serializers.ValidationError("Enter a valid phone number.")
        return normalized


class ConversationStatusSerializer(serializers.Serializer):
    status = serializers.ChoiceField(choices=Conversation.STATUS_CHOICES)
