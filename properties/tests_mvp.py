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
