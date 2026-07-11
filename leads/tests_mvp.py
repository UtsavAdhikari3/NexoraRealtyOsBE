from datetime import timedelta

from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from agencies.models import Agency
from leads.models import Lead, LeadInteraction, LeadPropertyInterest, LeadStatusHistory
from properties.models import Property
from users.models import AgencyUser


class LeadWorkflowMVPAPITestCase(APITestCase):
    def setUp(self):
        self.agency = Agency.objects.create(name="CRM Realty", license_number="CRM-001")
        self.other_agency = Agency.objects.create(name="Other", license_number="CRM-002")
        self.owner = AgencyUser.objects.create_user(
            email="crm-owner@example.com",
            password="Password123",
            full_name="CRM Owner",
            agency=self.agency,
            role=AgencyUser.ROLE_AGENCY_OWNER,
        )
        self.agent = AgencyUser.objects.create_user(
            email="crm-agent@example.com",
            password="Password123",
            full_name="CRM Agent",
            agency=self.agency,
            role=AgencyUser.ROLE_AGENT,
        )
        self.lead = Lead.objects.create(
            agency=self.agency,
            assigned_agent=self.agent,
            full_name="Buyer One",
            phone="9811111111",
        )
        self.property = Property.objects.create(
            agency=self.agency,
            title="CRM Property",
            property_type="house",
            purpose="sale",
            price="10000000",
            province="Bagmati",
            district="Kathmandu",
            city="Kathmandu",
        )
        self.interest = LeadPropertyInterest.objects.create(
            agency=self.agency,
            lead=self.lead,
            property=self.property,
        )

    def test_interest_detail_uses_interest_queryset(self):
        self.client.force_authenticate(user=self.agent)
        response = self.client.get(
            reverse("lead-property-interest-detail", kwargs={"pk": self.interest.id})
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["property"], self.property.id)

    def test_complete_follow_up_records_interaction_and_next_action(self):
        self.client.force_authenticate(user=self.agent)
        next_follow_up = timezone.now() + timedelta(days=2)
        response = self.client.post(
            reverse("lead-complete-follow-up", kwargs={"lead_id": self.lead.id}),
            {
                "note": "Buyer requested another call.",
                "interaction_type": "call",
                "next_follow_up_at": next_follow_up.isoformat(),
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.lead.refresh_from_db()
        self.assertEqual(self.lead.follow_up_status, Lead.FOLLOW_UP_PENDING)
        self.assertIsNotNone(self.lead.last_contacted_at)
        self.assertEqual(LeadInteraction.objects.filter(lead=self.lead).count(), 1)

    def test_status_change_creates_history_and_requires_lost_reason(self):
        self.client.force_authenticate(user=self.owner)
        url = reverse("lead-detail", kwargs={"pk": self.lead.id})
        invalid = self.client.patch(url, {"status": "lost"}, format="json")
        self.assertEqual(invalid.status_code, status.HTTP_400_BAD_REQUEST)

        valid = self.client.patch(
            url,
            {"status": "lost", "lost_reason": "Budget changed"},
            format="json",
        )
        self.assertEqual(valid.status_code, status.HTTP_200_OK)
        self.assertTrue(
            LeadStatusHistory.objects.filter(
                lead=self.lead,
                from_status="new",
                to_status="lost",
            ).exists()
        )
