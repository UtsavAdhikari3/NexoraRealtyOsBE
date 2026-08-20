from unittest.mock import patch

from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from agencies.models import Agency, AgencyDomain
from agencies.website_onboarding import default_website_config
from agencies.website_urls import agency_website_url
from users.models import AgencyUser


class AgencyDomainAPITests(APITestCase):
    def setUp(self):
        self.agency = Agency.objects.create(
            name="Domain Realty",
            license_number="DOMAIN-001",
            payment_status=Agency.PAYMENT_PAID,
            is_website_published=True,
            website_published_config=default_website_config(),
        )
        self.owner = AgencyUser.objects.create_user(
            email="domain-owner@example.com",
            password="Password123",
            full_name="Domain Owner",
            agency=self.agency,
            role=AgencyUser.ROLE_AGENCY_OWNER,
        )
        self.client.force_authenticate(self.owner)

    def test_claim_normalizes_and_globally_reserves_domain(self):
        response = self.client.post(reverse("website-domain-list"), {"domain": "HTTPS://Homes.Example.COM/path"})
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["domain"], "homes.example.com")
        self.assertEqual(response.data["verification_record"]["type"], "TXT")

        other = Agency.objects.create(name="Other", license_number="DOMAIN-002")
        other_owner = AgencyUser.objects.create_user(
            email="other-domain@example.com", password="Password123", full_name="Other",
            agency=other, role=AgencyUser.ROLE_AGENCY_OWNER,
        )
        self.client.force_authenticate(other_owner)
        duplicate = self.client.post(reverse("website-domain-list"), {"domain": "homes.example.com"})
        self.assertEqual(duplicate.status_code, status.HTTP_400_BAD_REQUEST)

    @patch("agencies.views.verify_domain_ownership", return_value=True)
    def test_verified_primary_domain_controls_resolution_and_canonical_url(self, verify):
        domain = AgencyDomain.objects.create(agency=self.agency, domain="homes.example.com")
        checked = self.client.post(reverse("website-domain-verify", kwargs={"pk": domain.pk}))
        primary = self.client.post(reverse("website-domain-primary", kwargs={"pk": domain.pk}))
        public = self.client.get(reverse("public-agency-detail-by-domain"), {"domain": "homes.example.com"})

        self.assertEqual(checked.status_code, status.HTTP_200_OK)
        self.assertEqual(primary.status_code, status.HTTP_200_OK)
        self.assertEqual(public.status_code, status.HTTP_200_OK)
        self.assertEqual(public.data["canonical_base_url"], "https://homes.example.com")
        self.assertEqual(agency_website_url(self.agency), "https://homes.example.com")
        verify.assert_called_once()

    def test_pending_domain_is_not_public_or_primary(self):
        domain = AgencyDomain.objects.create(agency=self.agency, domain="pending.example.com")
        primary = self.client.post(reverse("website-domain-primary", kwargs={"pk": domain.pk}))
        public = self.client.get(reverse("public-agency-detail-by-domain"), {"domain": domain.domain})
        self.assertEqual(primary.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(public.status_code, status.HTTP_404_NOT_FOUND)
