from django.core.cache import cache
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from agencies.models import Agency, AgencyDomain
from agencies.website_onboarding import default_website_config
from leads.models import Lead
from users.models import AgencyUser


class AgencyMVPAPITestCase(APITestCase):
    def setUp(self):
        cache.clear()
        self.agency = Agency.objects.create(
            name="Agency Profile",
            license_number="AG-MVP-001",
            payment_status=Agency.PAYMENT_PAID,
        )
        self.owner = AgencyUser.objects.create_user(
            email="agency-owner@example.com",
            password="Password123",
            full_name="Agency Owner",
            agency=self.agency,
            role=AgencyUser.ROLE_AGENCY_OWNER,
        )
        self.agent = AgencyUser.objects.create_user(
            email="agency-agent@example.com",
            password="Password123",
            full_name="Agency Agent",
            agency=self.agency,
            role=AgencyUser.ROLE_AGENT,
        )

    def tearDown(self):
        cache.clear()

    def test_owner_can_update_profile_but_not_payment(self):
        original_draft = default_website_config()
        original_draft["hero_title"] = "Existing website draft"
        original_published = default_website_config()
        original_published["hero_title"] = "Existing live website"
        self.agency.website_draft_config = original_draft
        self.agency.website_published_config = original_published
        self.agency.website_config = original_published
        self.agency.website_draft_revision = 4
        self.agency.save(update_fields=[
            "website_draft_config", "website_published_config", "website_config",
            "website_draft_revision",
        ])
        self.client.force_authenticate(user=self.owner)
        response = self.client.patch(
            reverse("current-agency"),
            {
                "about": "Trusted local agency",
                "payment_status": "cancelled",
                "website_template": "luxury-agency",
                "website_config": {"hero_title": "Find a remarkable home"},
                "is_website_published": True,
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.agency.refresh_from_db()
        self.assertEqual(self.agency.about, "Trusted local agency")
        self.assertEqual(self.agency.payment_status, Agency.PAYMENT_PAID)
        self.assertEqual(self.agency.website_draft_config, original_draft)
        self.assertEqual(self.agency.website_published_config, original_published)
        self.assertEqual(self.agency.website_config, original_published)
        self.assertEqual(self.agency.website_draft_revision, 4)

    def test_public_agency_can_resolve_custom_domain(self):
        AgencyDomain.objects.create(
            agency=self.agency,
            domain="homes.example.com",
            status=AgencyDomain.STATUS_VERIFIED,
            is_active=True,
            is_primary=True,
        )
        response = self.client.get("/api/public/agencies/by-domain/?domain=https://homes.example.com/path")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["slug"], self.agency.slug)

    def test_unpublished_website_is_not_public(self):
        self.agency.is_website_published = False
        self.agency.save(update_fields=["is_website_published"])
        response = self.client.get(
            reverse("public-agency-detail-by-slug", kwargs={"slug": self.agency.slug})
        )
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_public_agents_and_contact_capture(self):
        agents = self.client.get(
            reverse(
                "public-agent-list",
                kwargs={"license_number": self.agency.license_number},
            )
        )
        self.assertEqual(agents.status_code, status.HTTP_200_OK)
        self.assertEqual(len(agents.data), 1)

        contact = self.client.post(
            reverse(
                "public-agency-contact",
                kwargs={"license_number": self.agency.license_number},
            ),
            {"full_name": "Visitor", "phone": "+977 9800000000", "message": "Call me"},
            format="json",
        )
        self.assertEqual(contact.status_code, status.HTTP_201_CREATED)
        self.assertEqual(Lead.objects.get().phone, "+9779800000000")
