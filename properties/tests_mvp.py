from django.core.cache import cache
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from agencies.models import Agency
from leads.models import Lead, LeadInteraction, LeadPropertyInterest
from properties.models import Property, PropertyEvent
from users.models import AgencyUser


class PublicPropertyMVPAPITestCase(APITestCase):
    def setUp(self):
        cache.clear()
        self.agency = Agency.objects.create(
            name="Public Realty",
            license_number="PUB-MVP-001",
            payment_status=Agency.PAYMENT_PAID,
        )
        self.agent = AgencyUser.objects.create_user(
            email="public-agent@example.com",
            password="Password123",
            full_name="Public Agent",
            agency=self.agency,
            role=AgencyUser.ROLE_AGENT,
        )
        self.owner = AgencyUser.objects.create_user(
            email="public-owner@example.com",
            password="Password123",
            full_name="Public Owner",
            agency=self.agency,
            role=AgencyUser.ROLE_AGENCY_OWNER,
        )
        self.property = Property.objects.create(
            agency=self.agency,
            assigned_agent=self.agent,
            title="House in Lalitpur",
            property_type="house",
            purpose="sale",
            price="25000000",
            province="Bagmati",
            district="Lalitpur",
            city="Lalitpur",
            status="available",
            is_published=True,
        )

    def tearDown(self):
        cache.clear()

    def test_duplicate_public_inquiries_reuse_lead_and_interest(self):
        url = reverse(
            "public-property-inquiry",
            kwargs={
                "license_number": self.agency.license_number,
                "property_id": self.property.id,
            },
        )
        payload = {
            "full_name": "Ram Sharma",
            "phone": "+977 9812345678",
            "email": "ram@example.com",
            "message": "Please call me.",
        }

        first = self.client.post(url, payload, format="json")
        payload["phone"] = "9812345678"
        second = self.client.post(url, payload, format="json")

        self.assertEqual(first.status_code, status.HTTP_201_CREATED)
        self.assertEqual(second.status_code, status.HTTP_200_OK)
        self.assertEqual(Lead.objects.filter(agency=self.agency).count(), 1)
        self.assertEqual(LeadPropertyInterest.objects.count(), 1)
        self.assertEqual(LeadInteraction.objects.count(), 2)
        self.assertEqual(
            PropertyEvent.objects.filter(event_type="inquiry").count(),
            2,
        )

    def test_public_event_and_dashboard_summary(self):
        event_url = reverse(
            "public-property-event",
            kwargs={
                "license_number": self.agency.license_number,
                "property_id": self.property.id,
            },
        )
        event_response = self.client.post(
            event_url,
            {"event_type": "view", "visitor_id": "visitor-1"},
            format="json",
        )
        self.assertEqual(event_response.status_code, status.HTTP_201_CREATED)

        self.client.force_authenticate(user=self.agent)
        dashboard = self.client.get(reverse("dashboard-summary"))
        self.assertEqual(dashboard.status_code, status.HTTP_200_OK)
        self.assertEqual(dashboard.data["totals"]["property_views"], 1)

    def test_inactive_agency_properties_are_not_public(self):
        self.agency.is_active = False
        self.agency.save(update_fields=["is_active"])
        url = reverse(
            "public-property-detail",
            kwargs={
                "license_number": self.agency.license_number,
                "pk": self.property.id,
            },
        )
        self.assertEqual(self.client.get(url).status_code, status.HTTP_404_NOT_FOUND)

    def test_public_filter_options_returns_locations_without_queryset_conflict(self):
        response = self.client.get(
            reverse(
                "public-property-filter-options",
                kwargs={"license_number": self.agency.license_number},
            )
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn(
            {"value": "Bagmati", "label": "Bagmati", "count": 1},
            response.data["locations"]["provinces"],
        )
        self.assertIn(
            {"value": "Lalitpur", "label": "Lalitpur", "count": 1},
            response.data["locations"]["districts"],
        )
        self.assertTrue(response.data["property_types"])
        self.assertTrue(response.data["purposes"])

    def test_draft_must_be_made_available_before_publication(self):
        draft = Property.objects.create(
            agency=self.agency,
            title="Draft Property",
            property_type="house",
            purpose="sale",
            price="10000000",
            province="Bagmati",
            district="Kathmandu",
            city="Kathmandu",
            status="draft",
        )
        self.client.force_authenticate(user=self.owner)
        url = reverse("property-detail", kwargs={"pk": draft.id})

        invalid = self.client.patch(url, {"is_published": True}, format="json")
        self.assertEqual(invalid.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("is_published", invalid.data)

        valid = self.client.patch(
            url,
            {"status": "available", "is_published": True},
            format="json",
        )
        self.assertEqual(valid.status_code, status.HTTP_200_OK)
        draft.refresh_from_db()
        self.assertTrue(draft.is_published)
        self.assertIsNotNone(draft.published_at)

    def test_existing_draft_can_be_published_and_unpublished_across_public_api(self):
        draft = Property.objects.create(
            agency=self.agency,
            title="Previously Saved Draft",
            property_type="house",
            purpose="sale",
            price="12000000",
            province="Bagmati",
            district="Kathmandu",
            city="Kathmandu",
            status="draft",
            is_published=False,
        )
        manage_url = reverse("property-detail", kwargs={"pk": draft.pk})
        public_list_url = reverse(
            "public-property-list",
            kwargs={"license_number": self.agency.license_number},
        )
        public_detail_url = reverse(
            "public-property-share-detail",
            kwargs={"slug": self.agency.slug, "share_slug": draft.share_slug},
        )

        def public_ids():
            response = self.client.get(public_list_url)
            self.assertEqual(response.status_code, status.HTTP_200_OK)
            return {item["id"] for item in response.data["results"]}

        self.assertNotIn(draft.pk, public_ids())
        self.assertEqual(self.client.get(public_detail_url).status_code, status.HTTP_404_NOT_FOUND)

        self.client.force_authenticate(user=self.owner)
        published = self.client.patch(
            manage_url,
            {"status": "available", "is_published": True},
            format="json",
        )
        self.assertEqual(published.status_code, status.HTTP_200_OK)
        draft.refresh_from_db()
        first_published_at = draft.published_at
        self.assertTrue(draft.is_published)
        self.assertIsNotNone(draft.availability_verified_at)
        self.assertIsNotNone(draft.listing_expires_at)

        self.client.force_authenticate(user=None)
        self.assertIn(draft.pk, public_ids())
        self.assertEqual(self.client.get(public_detail_url).status_code, status.HTTP_200_OK)

        self.client.force_authenticate(user=self.owner)
        edited = self.client.patch(manage_url, {"title": "Edited While Published"}, format="json")
        self.assertEqual(edited.status_code, status.HTTP_200_OK)
        draft.refresh_from_db()
        self.assertEqual(draft.published_at, first_published_at)

        unpublished = self.client.patch(
            manage_url,
            {"status": "draft", "is_published": False},
            format="json",
        )
        self.assertEqual(unpublished.status_code, status.HTTP_200_OK)
        draft.refresh_from_db()
        self.assertFalse(draft.is_published)

        self.client.force_authenticate(user=None)
        self.assertNotIn(draft.pk, public_ids())
        self.assertEqual(self.client.get(public_detail_url).status_code, status.HTTP_404_NOT_FOUND)
