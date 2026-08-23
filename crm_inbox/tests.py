import hashlib
import hmac
import json
from unittest.mock import patch

from django.test import override_settings
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from agencies.models import Agency
from leads.models import Lead
from social_media.models import SocialAccount, SocialPost, SocialPublishResult
from users.models import AgencyUser

from .models import Conversation, SocialContact, SocialMessage, WebhookEvent


@override_settings(
    META_APP_SECRET="webhook-test-secret",
    META_WEBHOOK_VERIFY_TOKEN="verify-me",
    SOCIAL_PROFILE_LOOKUP_ENABLED=False,
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
        self.whatsapp = SocialAccount.objects.create(
            agency=self.agency,
            provider="meta",
            platform="whatsapp",
            external_id="phone-number-1",
            business_account_id="waba-1",
            phone_number_id="phone-number-1",
            display_phone_number="+977 9812345678",
            name="Inbox Realty WhatsApp",
            access_token="whatsapp-token",
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

    @override_settings(SOCIAL_PROFILE_LOOKUP_ENABLED=True)
    @patch(
        "crm_inbox.services.get_meta_messaging_profile",
        return_value={
            "first_name": "Aarav",
            "last_name": "Sharma",
            "profile_pic": "https://example.com/aarav.jpg",
        },
    )
    def test_facebook_sender_profile_enriches_contact_and_automatic_lead(self, profile_mock):
        response = self.signed_webhook(self.facebook_payload())
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        contact = SocialContact.objects.get()
        self.assertEqual(contact.display_name, "Aarav Sharma")
        self.assertEqual(contact.profile_image_url, "https://example.com/aarav.jpg")
        self.assertIsNotNone(contact.profile_synced_at)
        self.assertEqual(contact.linked_lead.full_name, "Aarav Sharma")
        profile_mock.assert_called_once_with(self.facebook, "fb-user-1")

        self.client.force_authenticate(user=self.owner)
        inbox = self.client.get(reverse("inbox-conversation-list"))
        self.assertEqual(inbox.data[0]["contact"]["display_label"], "Aarav Sharma")
        self.assertTrue(inbox.data[0]["contact"]["profile_available"])

    def test_inbound_referral_creates_one_attributed_lead(self):
        post = SocialPost.objects.create(
            agency=self.agency,
            social_account=self.facebook,
            platform="facebook",
            caption="Attributed listing",
            created_by=self.owner,
        )
        SocialPublishResult.objects.create(
            post=post,
            social_account=self.facebook,
            platform="facebook",
            status=SocialPublishResult.STATUS_PUBLISHED,
            external_post_id="page-1_post-1",
        )
        payload = self.facebook_payload()
        payload["entry"][0]["messaging"][0]["referral"] = {
            "source": "SHORTLINK",
            "post_id": "page-1_post-1",
        }

        self.signed_webhook(payload)
        self.signed_webhook(payload)

        conversation = Conversation.objects.get()
        self.assertEqual(conversation.source_social_post_id, post.id)
        self.assertIsNotNone(conversation.linked_lead_id)
        self.assertEqual(Lead.objects.count(), 1)
        lead = Lead.objects.get()
        self.assertEqual(lead.source, "facebook")
        self.assertEqual(lead.custom_data["source_social_post_id"], post.id)

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

    def whatsapp_payload(self, *, message_id="wamid.inbound-1"):
        return {
            "object": "whatsapp_business_account",
            "entry": [{
                "id": "waba-1",
                "changes": [{
                    "field": "messages",
                    "value": {
                        "messaging_product": "whatsapp",
                        "metadata": {
                            "display_phone_number": "+977 9812345678",
                            "phone_number_id": "phone-number-1",
                        },
                        "contacts": [{
                            "profile": {"name": "Sita Gurung"},
                            "wa_id": "9779800000000",
                        }],
                        "messages": [{
                            "from": "9779800000000",
                            "id": message_id,
                            "timestamp": str(int(timezone.now().timestamp())),
                            "type": "text",
                            "text": {"body": "Can I arrange a viewing?"},
                        }],
                    },
                }],
            }],
        }

    def test_whatsapp_message_creates_named_contact_and_phone_lead(self):
        first = self.signed_webhook(self.whatsapp_payload())
        second = self.signed_webhook(self.whatsapp_payload())

        self.assertEqual(first.status_code, status.HTTP_200_OK)
        self.assertEqual(second.status_code, status.HTTP_200_OK)
        contact = SocialContact.objects.get(social_account=self.whatsapp)
        conversation = Conversation.objects.get(social_account=self.whatsapp)
        self.assertEqual(contact.display_name, "Sita Gurung")
        self.assertEqual(conversation.platform, "whatsapp")
        self.assertEqual(conversation.unread_count, 1)
        self.assertEqual(conversation.messages.get().text, "Can I arrange a viewing?")
        self.assertEqual(conversation.linked_lead.phone, "+9779800000000")
        self.assertEqual(conversation.linked_lead.source, "whatsapp")

        self.client.force_authenticate(user=self.owner)
        inbox = self.client.get(reverse("inbox-conversation-list"))
        whatsapp_conversation = next(
            item for item in inbox.data if item["platform"] == "whatsapp"
        )
        self.assertEqual(whatsapp_conversation["contact"]["phone"], "+9779800000000")

    @patch(
        "crm_inbox.views.send_meta_text_message",
        return_value={"message_id": "wamid.outbound-1"},
    )
    def test_whatsapp_reply_is_allowed_inside_service_window(self, send_mock):
        self.signed_webhook(self.whatsapp_payload())
        conversation = Conversation.objects.get(social_account=self.whatsapp)
        self.client.force_authenticate(user=self.owner)

        response = self.client.post(
            reverse("inbox-reply", kwargs={"conversation_id": conversation.id}),
            {"text": "Yes, which day works for you?"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["provider_message_id"], "wamid.outbound-1")
        send_mock.assert_called_once_with(
            self.whatsapp,
            "9779800000000",
            "Yes, which day works for you?",
        )

    def test_whatsapp_reply_requires_template_after_service_window(self):
        self.signed_webhook(self.whatsapp_payload())
        conversation = Conversation.objects.get(social_account=self.whatsapp)
        conversation.messages.update(
            sent_at=timezone.now() - timezone.timedelta(hours=25)
        )
        self.client.force_authenticate(user=self.owner)

        response = self.client.post(
            reverse("inbox-reply", kwargs={"conversation_id": conversation.id}),
            {"text": "Following up"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_409_CONFLICT)
        self.assertEqual(response.data["code"], "whatsapp_service_window_closed")

    def test_whatsapp_delivery_receipt_updates_outbound_message(self):
        self.signed_webhook(self.whatsapp_payload())
        conversation = Conversation.objects.get(social_account=self.whatsapp)
        message = SocialMessage.objects.create(
            conversation=conversation,
            social_account=self.whatsapp,
            provider_message_id="wamid.outbound-status",
            direction=SocialMessage.DIRECTION_OUTBOUND,
            message_type=SocialMessage.TYPE_TEXT,
            text="Hello",
            delivery_status=SocialMessage.STATUS_SENT,
            sent_at=timezone.now(),
        )
        receipt = {
            "object": "whatsapp_business_account",
            "entry": [{
                "id": "waba-1",
                "changes": [{
                    "field": "messages",
                    "value": {
                        "metadata": {"phone_number_id": "phone-number-1"},
                        "statuses": [{
                            "id": "wamid.outbound-status",
                            "status": "read",
                            "timestamp": str(int(timezone.now().timestamp())),
                            "recipient_id": "9779800000000",
                        }],
                    },
                }],
            }],
        }
        response = self.signed_webhook(receipt)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        message.refresh_from_db()
        self.assertEqual(message.delivery_status, SocialMessage.STATUS_READ)

    @override_settings(SOCIAL_PROFILE_LOOKUP_ENABLED=True)
    @patch(
        "crm_inbox.services.get_meta_messaging_profile",
        return_value={
            "name": "Maya Rai",
            "username": "maya.homes",
            "profile_pic": "https://example.com/maya.jpg",
            "follower_count": 2450,
            "is_verified_user": True,
            "private_field": "must-not-be-stored",
        },
    )
    def test_instagram_profile_stores_only_safe_public_details(self, profile_mock):
        payload = {
            "object": "instagram",
            "entry": [{
                "id": "ig-1",
                "messaging": [{
                    "sender": {"id": "ig-user-profile"},
                    "recipient": {"id": "ig-1"},
                    "timestamp": 1783900001000,
                    "message": {"mid": "ig-profile-mid", "text": "Hello"},
                }],
            }],
        }
        self.signed_webhook(payload)
        contact = SocialContact.objects.get()
        self.assertEqual(contact.display_name, "Maya Rai")
        self.assertEqual(contact.username, "maya.homes")
        self.assertEqual(
            contact.profile_data,
            {"follower_count": 2450, "is_verified_user": True},
        )

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

    @override_settings(SOCIAL_AUTO_CREATE_LEADS=False)
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
