from django.test import override_settings
from rest_framework import status
from rest_framework.test import APIRequestFactory, APITestCase

from agencies.models import Agency
from agencies.views import TestMarkAgencyPaidView
from users.models import AgencyUser


class TestMarkAgencyPaidAPITestCase(APITestCase):
    def setUp(self):
        self.agency = Agency.objects.create(
            name="Nexora Test Realty",
            license_number="TEST-001",
        )
        self.user = AgencyUser.objects.create_user(
            email="owner@example.com",
            password="Password123",
            full_name="Test Owner",
            agency=self.agency,
            role=AgencyUser.ROLE_AGENCY_OWNER,
        )
        self.url = "/api/agencies/test/mark-paid/"

    @override_settings(DEBUG=True)
    def test_marks_agency_paid_in_debug_mode(self):
        request = APIRequestFactory().post(
            self.url,
            {
                "email": self.user.email,
                "license_number": self.agency.license_number,
                "verify_email": True,
            },
            format="json",
        )
        response = TestMarkAgencyPaidView.as_view()(request)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.agency.refresh_from_db()
        self.user.refresh_from_db()
        self.assertEqual(self.agency.payment_status, Agency.PAYMENT_PAID)
        self.assertIsNotNone(self.agency.paid_at)
        self.assertTrue(self.user.is_email_verified)

    @override_settings(DEBUG=False)
    def test_is_not_available_outside_debug_mode(self):
        response = self.client.post(
            self.url,
            {
                "email": self.user.email,
                "license_number": self.agency.license_number,
                "verify_email": True,
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.agency.refresh_from_db()
        self.assertEqual(self.agency.payment_status, Agency.PAYMENT_UNPAID)
