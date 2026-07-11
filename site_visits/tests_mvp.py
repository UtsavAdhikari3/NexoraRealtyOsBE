from datetime import timedelta

from django.core import mail
from django.core.management import call_command
from django.test import override_settings
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from agencies.models import Agency
from leads.models import Lead, LeadStatusHistory
from properties.models import Property
from site_visits.models import SiteVisit
from users.models import AgencyUser


@override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
class SiteVisitMVPAPITestCase(APITestCase):
    def setUp(self):
        self.agency = Agency.objects.create(
            name="Visit Realty",
            license_number="VISIT-001",
            payment_status=Agency.PAYMENT_PAID,
        )
        self.owner = AgencyUser.objects.create_user(
            email="visit-owner@example.com",
            password="Password123",
            full_name="Visit Owner",
            agency=self.agency,
            role=AgencyUser.ROLE_AGENCY_OWNER,
        )
        self.agent = AgencyUser.objects.create_user(
            email="visit-agent@example.com",
            password="Password123",
            full_name="Visit Agent",
            agency=self.agency,
            role=AgencyUser.ROLE_AGENT,
        )
        self.lead = Lead.objects.create(
            agency=self.agency,
            assigned_agent=self.agent,
            full_name="Visit Buyer",
            phone="9800000001",
            email="buyer@example.com",
        )
        self.property = Property.objects.create(
            agency=self.agency,
            title="Visit Property",
            property_type="house",
            purpose="sale",
            price="10000000",
            province="Bagmati",
            district="Kathmandu",
            city="Kathmandu",
        )
        self.visit = SiteVisit.objects.create(
            agency=self.agency,
            lead=self.lead,
            property=self.property,
            assigned_agent=self.agent,
            scheduled_at=timezone.now() + timedelta(hours=2),
            status="scheduled",
        )

    def test_completion_updates_lead_and_status_history(self):
        self.client.force_authenticate(user=self.owner)
        response = self.client.patch(
            reverse("site-visit-detail", kwargs={"pk": self.visit.id}),
            {"status": "completed", "outcome": "Buyer is interested."},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.visit.refresh_from_db()
        self.lead.refresh_from_db()
        self.assertIsNotNone(self.visit.completed_at)
        self.assertEqual(self.lead.status, "site_visit_completed")
        self.assertTrue(LeadStatusHistory.objects.filter(lead=self.lead).exists())

    def test_cancellation_requires_reason(self):
        self.client.force_authenticate(user=self.owner)
        response = self.client.patch(
            reverse("site-visit-detail", kwargs={"pk": self.visit.id}),
            {"status": "cancelled"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_reminder_command_is_idempotent(self):
        call_command("send_due_reminders", hours=24)
        call_command("send_due_reminders", hours=24)
        self.visit.refresh_from_db()
        self.assertIsNotNone(self.visit.reminder_sent_at)
        self.assertEqual(len(mail.outbox), 1)
