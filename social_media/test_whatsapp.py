from unittest.mock import patch

from django.test import override_settings
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from agencies.models import Agency
from social_media.models import SocialAccount, SocialOAuthState
from social_media.services.meta import send_meta_text_message
from users.models import AgencyUser


@override_settings(
    META_APP_ID="meta-app-id",
    META_APP_SECRET="meta-app-secret",
    META_GRAPH_VERSION="v23.0",
    META_WHATSAPP_LOGIN_CONFIG_ID="whatsapp-config-id",
)
class WhatsAppConnectionAPITestCase(APITestCase):
    def setUp(self):
        self.agency = Agency.objects.create(
            name="WhatsApp Realty",
            license_number="WA-001",
        )
        self.owner = AgencyUser.objects.create_user(
            email="wa-owner@example.com",
            password="Password123",
            full_name="WA Owner",
            agency=self.agency,
            role=AgencyUser.ROLE_AGENCY_OWNER,
        )
        self.agent = AgencyUser.objects.create_user(
            email="wa-agent@example.com",
            password="Password123",
            full_name="WA Agent",
            agency=self.agency,
            role=AgencyUser.ROLE_AGENT,
        )

    def test_only_owner_or_manager_can_start_whatsapp_connection(self):
        self.client.force_authenticate(user=self.agent)
        denied = self.client.get(reverse("whatsapp-connection-start"))
        self.assertEqual(denied.status_code, status.HTTP_403_FORBIDDEN)

        self.client.force_authenticate(user=self.owner)
        response = self.client.get(reverse("whatsapp-connection-start"))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["app_id"], "meta-app-id")
        self.assertEqual(response.data["config_id"], "whatsapp-config-id")
        self.assertTrue(
            SocialOAuthState.objects.filter(
                state=response.data["state"],
                provider="whatsapp",
                user=self.owner,
            ).exists()
        )

    @patch("social_media.views.subscribe_whatsapp_business_account")
    @patch("social_media.views.get_whatsapp_phone_numbers")
    @patch("social_media.views.exchange_whatsapp_signup_code")
    def test_embedded_signup_connects_selected_phone(
        self,
        exchange_mock,
        phone_numbers_mock,
        subscribe_mock,
    ):
        exchange_mock.return_value = {
            "access_token": "whatsapp-access-token",
            "expires_in": 3600,
        }
        phone_numbers_mock.return_value = [{
            "id": "phone-number-1",
            "verified_name": "WhatsApp Realty",
            "display_phone_number": "+977 9812345678",
            "quality_rating": "GREEN",
        }]
        subscribe_mock.return_value = {"success": True}
        self.client.force_authenticate(user=self.owner)
        state = self.client.get(reverse("whatsapp-connection-start")).data["state"]

        response = self.client.post(
            reverse("whatsapp-connection-complete"),
            {
                "state": state,
                "code": "embedded-signup-code",
                "business_account_id": "waba-1",
                "phone_number_id": "phone-number-1",
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        account = SocialAccount.objects.get(platform="whatsapp")
        self.assertEqual(account.business_account_id, "waba-1")
        self.assertEqual(account.phone_number_id, "phone-number-1")
        self.assertEqual(account.display_phone_number, "+977 9812345678")
        self.assertEqual(account.webhook_subscription_status, "subscribed")
        subscribe_mock.assert_called_once_with("waba-1", "whatsapp-access-token")

    @patch("social_media.services.meta.requests.post")
    def test_send_whatsapp_text_uses_cloud_api_payload(self, post_mock):
        post_mock.return_value.ok = True
        post_mock.return_value.json.return_value = {
            "messages": [{"id": "wamid.sent-1"}],
        }
        account = SocialAccount.objects.create(
            agency=self.agency,
            provider="meta",
            platform="whatsapp",
            external_id="phone-number-1",
            phone_number_id="phone-number-1",
            business_account_id="waba-1",
            access_token="whatsapp-access-token",
        )

        result = send_meta_text_message(account, "9779800000000", "Hello")

        self.assertEqual(result["message_id"], "wamid.sent-1")
        _, kwargs = post_mock.call_args
        self.assertEqual(kwargs["json"]["messaging_product"], "whatsapp")
        self.assertEqual(kwargs["json"]["to"], "9779800000000")
        self.assertEqual(kwargs["json"]["text"]["body"], "Hello")
