import json
import uuid

from django.db.models import Q
from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import generics, serializers, status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from leads.models import Lead, LeadInteraction, LeadStatusHistory
from social_media.services.meta import MetaAPIError, send_meta_text_message
from users.models import AgencyUser

from .models import Conversation, SocialMessage
from .serializers import (
    AssignConversationSerializer,
    ConversationSerializer,
    ConversationStatusSerializer,
    CreateLeadFromConversationSerializer,
    LinkLeadSerializer,
    ReplySerializer,
    SocialMessageSerializer,
)
from .services import record_and_process_webhook, verify_meta_signature


class MetaWebhookSerializer(serializers.Serializer):
    """Schema placeholder for Meta's polymorphic webhook payloads."""


def get_accessible_conversations(user):
    if not user.agency_id:
        return Conversation.objects.none()
    queryset = Conversation.objects.filter(agency=user.agency)
    if user.role == AgencyUser.ROLE_AGENT:
        queryset = queryset.filter(
            Q(assigned_agent=user) | Q(assigned_agent__isnull=True)
        )
    return queryset


class MetaWebhookView(APIView):
    # Meta sends several webhook payload shapes, so this endpoint intentionally
    # accepts an unstructured JSON object instead of a product-facing serializer.
    serializer_class = MetaWebhookSerializer
    permission_classes = [AllowAny]
    authentication_classes = []
    throttle_scope = "meta_webhook"

    def get(self, request):
        mode = request.query_params.get("hub.mode")
        token = request.query_params.get("hub.verify_token")
        challenge = request.query_params.get("hub.challenge")
        from django.conf import settings

        if (
            mode == "subscribe"
            and settings.META_WEBHOOK_VERIFY_TOKEN
            and token == settings.META_WEBHOOK_VERIFY_TOKEN
        ):
            return HttpResponse(challenge or "", content_type="text/plain")
        return Response({"detail": "Invalid webhook verification token."}, status=403)

    def post(self, request):
        raw_body = request.body
        signature = request.headers.get("X-Hub-Signature-256", "")
        if not verify_meta_signature(raw_body, signature):
            return Response({"detail": "Invalid webhook signature."}, status=403)
        try:
            event, created = record_and_process_webhook(raw_body)
        except (json.JSONDecodeError, UnicodeDecodeError):
            return Response({"detail": "Invalid JSON payload."}, status=400)

        return Response(
            {
                "status": event.status,
                "event_id": event.id,
                "created": created,
            }
        )


class ConversationListView(generics.ListAPIView):
    serializer_class = ConversationSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        queryset = get_accessible_conversations(self.request.user).select_related(
            "social_account",
            "contact",
            "assigned_agent",
            "linked_lead",
        )
        platform = self.request.query_params.get("platform")
        status_value = self.request.query_params.get("status")
        assigned_agent = self.request.query_params.get("assigned_agent")
        unread = self.request.query_params.get("unread")
        search = self.request.query_params.get("search")

        if platform:
            queryset = queryset.filter(platform=platform)
        if status_value:
            queryset = queryset.filter(status=status_value)
        if assigned_agent == "unassigned":
            queryset = queryset.filter(assigned_agent__isnull=True)
        elif assigned_agent and assigned_agent.isdigit():
            queryset = queryset.filter(assigned_agent_id=int(assigned_agent))
        if unread == "true":
            queryset = queryset.filter(unread_count__gt=0)
        if search:
            queryset = queryset.filter(
                Q(contact__display_name__icontains=search)
                | Q(contact__username__icontains=search)
                | Q(last_message_preview__icontains=search)
                | Q(linked_lead__full_name__icontains=search)
            )
        return queryset


class ConversationDetailView(generics.RetrieveAPIView):
    serializer_class = ConversationSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return get_accessible_conversations(self.request.user).select_related(
            "social_account", "contact", "assigned_agent", "linked_lead"
        )


class ConversationMessagesView(generics.ListAPIView):
    serializer_class = SocialMessageSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        conversation = get_object_or_404(
            get_accessible_conversations(self.request.user),
            id=self.kwargs["conversation_id"],
        )
        return conversation.messages.all()


class ConversationReplyView(APIView):
    permission_classes = [IsAuthenticated]
    serializer_class = ReplySerializer

    def post(self, request, conversation_id):
        conversation = get_object_or_404(
            get_accessible_conversations(request.user).select_related(
                "social_account", "contact"
            ),
            id=conversation_id,
        )
        serializer = self.serializer_class(data=request.data)
        serializer.is_valid(raise_exception=True)
        text = serializer.validated_data["text"]
        message = SocialMessage.objects.create(
            conversation=conversation,
            social_account=conversation.social_account,
            provider_message_id=f"local:{uuid.uuid4().hex}",
            direction=SocialMessage.DIRECTION_OUTBOUND,
            message_type=SocialMessage.TYPE_TEXT,
            sender_external_id=conversation.social_account.external_id,
            text=text,
            delivery_status=SocialMessage.STATUS_PENDING,
            sent_at=timezone.now(),
        )

        try:
            provider_response = send_meta_text_message(
                conversation.social_account,
                conversation.contact.external_user_id,
                text,
            )
            provider_message_id = provider_response.get("message_id")
            if not provider_message_id:
                raise MetaAPIError("Meta did not return a message ID.")
            message.provider_message_id = provider_message_id
            message.delivery_status = SocialMessage.STATUS_SENT
            message.error_message = ""
        except Exception as exc:
            message.delivery_status = SocialMessage.STATUS_FAILED
            message.error_message = str(exc)
        message.save()

        conversation.last_message_at = message.sent_at
        conversation.last_message_preview = text[:255]
        conversation.status = Conversation.STATUS_PENDING
        conversation.save(
            update_fields=[
                "last_message_at",
                "last_message_preview",
                "status",
                "updated_at",
            ]
        )
        if conversation.linked_lead_id:
            LeadInteraction.objects.create(
                agency=conversation.agency,
                lead=conversation.linked_lead,
                agent=request.user,
                interaction_type=conversation.platform,
                direction="outbound",
                note=text,
            )
            lead = conversation.linked_lead
            lead.last_contacted_at = message.sent_at
            lead.save(update_fields=["last_contacted_at", "updated_at"])
        response_status = (
            status.HTTP_201_CREATED
            if message.delivery_status == SocialMessage.STATUS_SENT
            else status.HTTP_502_BAD_GATEWAY
        )
        return Response(SocialMessageSerializer(message).data, status=response_status)


class ConversationAssignView(APIView):
    permission_classes = [IsAuthenticated]
    serializer_class = AssignConversationSerializer

    def post(self, request, conversation_id):
        conversation = get_object_or_404(
            get_accessible_conversations(request.user),
            id=conversation_id,
        )
        serializer = self.serializer_class(
            data=request.data,
            context={"conversation": conversation},
        )
        serializer.is_valid(raise_exception=True)
        agent = serializer.validated_data["assigned_agent"]

        if request.user.role == AgencyUser.ROLE_AGENT and agent != request.user:
            return Response({"detail": "Agents can only claim a conversation."}, status=403)
        conversation.assigned_agent = agent
        conversation.save(update_fields=["assigned_agent", "updated_at"])
        return Response(ConversationSerializer(conversation).data)


class ConversationLinkLeadView(APIView):
    permission_classes = [IsAuthenticated]
    serializer_class = LinkLeadSerializer

    def post(self, request, conversation_id):
        conversation = get_object_or_404(
            get_accessible_conversations(request.user).select_related("contact"),
            id=conversation_id,
        )
        serializer = self.serializer_class(
            data=request.data,
            context={"conversation": conversation},
        )
        serializer.is_valid(raise_exception=True)
        lead = serializer.validated_data["lead"]
        conversation.linked_lead = lead
        conversation.contact.linked_lead = lead
        conversation.save(update_fields=["linked_lead", "updated_at"])
        conversation.contact.save(update_fields=["linked_lead"])
        if conversation.last_message_at and (
            not lead.last_contacted_at or conversation.last_message_at > lead.last_contacted_at
        ):
            lead.last_contacted_at = conversation.last_message_at
            lead.save(update_fields=["last_contacted_at", "updated_at"])
        return Response(ConversationSerializer(conversation).data)


class ConversationCreateLeadView(APIView):
    permission_classes = [IsAuthenticated]
    serializer_class = CreateLeadFromConversationSerializer

    def post(self, request, conversation_id):
        conversation = get_object_or_404(
            get_accessible_conversations(request.user).select_related("contact"),
            id=conversation_id,
        )
        if conversation.linked_lead_id:
            return Response({"detail": "Conversation is already linked to a lead."}, status=400)
        serializer = self.serializer_class(data=request.data)
        serializer.is_valid(raise_exception=True)
        lead = Lead.objects.create(
            agency=conversation.agency,
            assigned_agent=conversation.assigned_agent,
            created_by=request.user,
            source=conversation.platform,
            status="new",
            last_contacted_at=conversation.last_message_at,
            **serializer.validated_data,
        )
        LeadStatusHistory.objects.create(
            agency=conversation.agency,
            lead=lead,
            to_status=lead.status,
            changed_by=request.user,
        )
        conversation.linked_lead = lead
        conversation.contact.linked_lead = lead
        conversation.save(update_fields=["linked_lead", "updated_at"])
        conversation.contact.save(update_fields=["linked_lead"])
        LeadInteraction.objects.create(
            agency=conversation.agency,
            lead=lead,
            agent=request.user,
            interaction_type="note",
            direction="internal",
            note=f"Lead created from {conversation.platform} conversation.",
        )
        return Response(ConversationSerializer(conversation).data, status=201)


class ConversationMarkReadView(APIView):
    permission_classes = [IsAuthenticated]
    serializer_class = ConversationSerializer

    def post(self, request, conversation_id):
        conversation = get_object_or_404(
            get_accessible_conversations(request.user),
            id=conversation_id,
        )
        conversation.unread_count = 0
        conversation.save(update_fields=["unread_count", "updated_at"])
        return Response(ConversationSerializer(conversation).data)


class ConversationStatusView(APIView):
    permission_classes = [IsAuthenticated]
    serializer_class = ConversationStatusSerializer

    def post(self, request, conversation_id):
        conversation = get_object_or_404(
            get_accessible_conversations(request.user),
            id=conversation_id,
        )
        serializer = self.serializer_class(data=request.data)
        serializer.is_valid(raise_exception=True)
        conversation.status = serializer.validated_data["status"]
        conversation.save(update_fields=["status", "updated_at"])
        return Response(ConversationSerializer(conversation).data)
