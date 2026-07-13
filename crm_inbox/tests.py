import hashlib
import hmac
import json
from unittest.mock import patch

from django.test import override_settings
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from agencies.models import Agency
from leads.models import Lead
from social_media.models import SocialAccount
from users.models import AgencyUser

from .models import Conversation, SocialContact, SocialMessage, WebhookEvent


@override_settings(
    META_APP_SECRET="webhook-test-secret",
    META_WEBHOOK_VERIFY_TOKEN="verify-me",
)
class UnifiedInboxAPITestCase(APITestCase):
    def setUp(self):
        self.agency = Agency.objects.create(name="Inbox Realty", license_number="INBOX-001")
        self.other_agency = Agency.objects.create(name="Other Inbox", license_number="INBOX-002")
        self.owner = AgencyUser.objects.create_user(
            email="inbox-owner@example.com",
            password="Password123",
            full_name="Inbox Owner",
            agency=self.agency,
            role=AgencyUser.ROLE_AGENCY_OWNER,
        )
        self.agent = AgencyUser.objects.create_user(
            email="inbox-agent@example.com",
            password="Password123",
            full_name="Inbox Agent",
            agency=self.agency,
            role=AgencyUser.ROLE_AGENT,
        )
        self.other_owner = AgencyUser.objects.create_user(
            email="other-inbox-owner@example.com",
            password="Password123",
            full_name="Other Owner",
            agency=self.other_agency,
            role=AgencyUser.ROLE_AGENCY_OWNER,
        )
        self.facebook = SocialAccount.objects.create(
            agency=self.agency,
            provider="meta",
            platform="facebook",
            external_id="page-1",
            page_id="page-1",
            name="Facebook Page",
            access_token="page-token",
        )
        self.instagram = SocialAccount.objects.create(
            agency=self.agency,
            provider="meta",
            platform="instagram",
            external_id="ig-1",
            page_id="page-1",
            name="Instagram Account",
            username="inboxrealty",
            access_token="page-token",
        )

    def signed_webhook(self, payload):
        raw = json.dumps(payload, separators=(",", ":")).encode("utf-8")
        signature = hmac.new(
            b"webhook-test-secret",
            raw,
            hashlib.sha256,
        ).hexdigest()
        return self.client.generic(
            "POST",
            reverse("meta-webhook"),
            data=raw,
            content_type="application/json",
            HTTP_X_HUB_SIGNATURE_256=f"sha256={signature}",
        )

    def facebook_payload(self):
        return {
            "object": "page",
            "entry": [
                {
                    "id": "page-1",
                    "messaging": [
                        {
                            "sender": {"id": "fb-user-1"},
                            "recipient": {"id": "page-1"},
                            "timestamp": 1783900000000,
                            "message": {
                                "mid": "fb-mid-1",
                                "text": "Is the property still available?",
                            },
                        }
                    ],
                }
            ],
        }

    def test_webhook_verification_returns_plain_challenge(self):
        response = self.client.get(
            reverse("meta-webhook"),
            {
                "hub.mode": "subscribe",
                "hub.verify_token": "verify-me",
                "hub.challenge": "123456",
            },
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.content, b"123456")

    def test_invalid_webhook_signature_is_rejected(self):
        response = self.client.generic(
            "POST",
            reverse("meta-webhook"),
            data=b"{}",
            content_type="application/json",
            HTTP_X_HUB_SIGNATURE_256="sha256=invalid",
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_facebook_message_is_ingested_once(self):
        first = self.signed_webhook(self.facebook_payload())
        second = self.signed_webhook(self.facebook_payload())

        self.assertEqual(first.status_code, status.HTTP_200_OK)
        self.assertEqual(second.status_code, status.HTTP_200_OK)
        self.assertEqual(WebhookEvent.objects.count(), 1)
        self.assertEqual(SocialContact.objects.count(), 1)
        self.assertEqual(Conversation.objects.count(), 1)
        self.assertEqual(SocialMessage.objects.count(), 1)
        conversation = Conversation.objects.get()
        self.assertEqual(conversation.platform, "facebook")
        self.assertEqual(conversation.unread_count, 1)

    def test_instagram_message_is_normalized_into_same_inbox(self):
        payload = {
            "object": "instagram",
            "entry": [
                {
                    "id": "ig-1",
                    "messaging": [
                        {
                            "sender": {"id": "ig-user-1"},
                            "recipient": {"id": "ig-1"},
                            "timestamp": 1783900001000,
                            "message": {"mid": "ig-mid-1", "text": "Price please"},
                        }
                    ],
                }
            ],
        }
        response = self.signed_webhook(payload)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        conversation = Conversation.objects.get()
        self.assertEqual(conversation.platform, "instagram")
        self.assertEqual(conversation.messages.get().text, "Price please")

    def test_conversations_are_tenant_scoped(self):
        self.signed_webhook(self.facebook_payload())
        self.client.force_authenticate(user=self.other_owner)
        response = self.client.get(reverse("inbox-conversation-list"))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 0)

    @patch(
        "crm_inbox.views.send_meta_text_message",
        return_value={"message_id": "outbound-mid-1"},
    )
    def test_agent_can_claim_and_reply_to_conversation(self, send_mock):
        self.signed_webhook(self.facebook_payload())
        conversation = Conversation.objects.get()
        self.client.force_authenticate(user=self.agent)

        claim = self.client.post(
            reverse("inbox-assign", kwargs={"conversation_id": conversation.id}),
            {"assigned_agent": self.agent.id},
            format="json",
        )
        self.assertEqual(claim.status_code, status.HTTP_200_OK)

        reply = self.client.post(
            reverse("inbox-reply", kwargs={"conversation_id": conversation.id}),
            {"text": "Yes, it is available."},
            format="json",
        )
        self.assertEqual(reply.status_code, status.HTTP_201_CREATED)
        self.assertEqual(reply.data["delivery_status"], "sent")
        send_mock.assert_called_once()

    def test_create_lead_and_mark_conversation_read(self):
        self.signed_webhook(self.facebook_payload())
        conversation = Conversation.objects.get()
        self.client.force_authenticate(user=self.owner)
        create_lead = self.client.post(
            reverse("inbox-create-lead", kwargs={"conversation_id": conversation.id}),
            {
                "full_name": "Facebook Buyer",
                "phone": "+977 9812345678",
                "email": "buyer@example.com",
            },
            format="json",
        )
        self.assertEqual(create_lead.status_code, status.HTTP_201_CREATED)
        conversation.refresh_from_db()
        self.assertIsNotNone(conversation.linked_lead_id)
        self.assertEqual(Lead.objects.get(id=conversation.linked_lead_id).source, "facebook")

        mark_read = self.client.post(
            reverse("inbox-mark-read", kwargs={"conversation_id": conversation.id}),
            {},
            format="json",
        )
        self.assertEqual(mark_read.status_code, status.HTTP_200_OK)
        self.assertEqual(mark_read.data["unread_count"], 0)
