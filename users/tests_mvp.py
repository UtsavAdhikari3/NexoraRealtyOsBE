from datetime import timedelta

from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase
from rest_framework_simplejwt.tokens import RefreshToken

from agencies.models import Agency
from users.models import AgencyUser


class SubscriptionAuthenticationMVPAPITestCase(APITestCase):
    def test_existing_jwt_is_rejected_after_subscription_expires(self):
        agency = Agency.objects.create(
            name="Expired Realty",
            license_number="EXP-001",
            payment_status=Agency.PAYMENT_PAID,
            subscription_expires_at=timezone.now() + timedelta(days=1),
        )
        user = AgencyUser.objects.create_user(
            email="expired-owner@example.com",
            password="Password123",
            full_name="Expired Owner",
            agency=agency,
            role=AgencyUser.ROLE_AGENCY_OWNER,
            is_email_verified=True,
        )
        token = str(RefreshToken.for_user(user).access_token)
        agency.subscription_expires_at = timezone.now() - timedelta(seconds=1)
        agency.save(update_fields=["subscription_expires_at"])

        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
        response = self.client.get(reverse("current-agency"))
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
