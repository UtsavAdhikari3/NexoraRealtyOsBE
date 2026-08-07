from datetime import timedelta

from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APITestCase

from agencies.models import Agency
from operations.models import Deal, Document, Offer
from properties.models import Property
from site_visits.models import SiteVisit
from users.models import AgencyUser
from .models import Lead, LeadInteraction, LeadPropertyInterest


class UnifiedLeadInboxTests(APITestCase):
    def setUp(self):
        self.agency = Agency.objects.create(
            name="Inbox Realty",
            license_number="INBOX-001",
            payment_status="paid",
        )
        self.manager = AgencyUser.objects.create_user(
            email="inbox-manager@example.com",
            password="Password123",
            full_name="Inbox Manager",
            agency=self.agency,
            role="agency_manager",
        )
        self.agent = AgencyUser.objects.create_user(
            email="inbox-agent@example.com",
            password="Password123",
            full_name="Inbox Agent",
            agency=self.agency,
            role="agent",
        )
        self.property = Property.objects.create(
            agency=self.agency,
            assigned_agent=self.agent,
            title="Lalitpur Family Home",
            property_type="house",
            purpose="sale",
            price=25000000,
            province="Bagmati",
            district="Lalitpur",
            city="Lalitpur",
            municipality="Lalitpur Metropolitan City",
            address="Ward 3",
        )
        self.lead = Lead.objects.create(
            agency=self.agency,
            assigned_agent=self.agent,
            created_by=self.manager,
            full_name="Viber Buyer",
            phone="9800000000",
            source="viber",
            status="interested",
            next_follow_up_at=timezone.now() + timedelta(days=1),
            follow_up_status=Lead.FOLLOW_UP_PENDING,
        )
        LeadPropertyInterest.objects.create(
            agency=self.agency,
            lead=self.lead,
            property=self.property,
            interest_level="hot",
        )
        LeadInteraction.objects.create(
            agency=self.agency,
            lead=self.lead,
            agent=self.agent,
            interaction_type="viber",
            direction="inbound",
            note="Asked whether the road is blacktopped.",
        )
        SiteVisit.objects.create(
            agency=self.agency,
            lead=self.lead,
            property=self.property,
            assigned_agent=self.agent,
            scheduled_at=timezone.now() + timedelta(days=2),
            created_by=self.manager,
        )
        self.deal = Deal.objects.create(
            agency=self.agency,
            lead=self.lead,
            property=self.property,
            assigned_agent=self.agent,
            title="Viber Buyer - Family Home",
            stage="negotiation",
            value=24000000,
        )
        Offer.objects.create(
            agency=self.agency,
            deal=self.deal,
            amount=23500000,
            status="countered",
            submitted_by=self.agent,
        )
        Document.objects.create(
            agency=self.agency,
            lead=self.lead,
            title="Buyer citizenship",
            category="identity",
            file=SimpleUploadedFile("citizenship.pdf", b"%PDF-test", "application/pdf"),
            uploaded_by=self.manager,
        )
        self.client.force_authenticate(self.manager)

    def test_lead_summary_contains_unified_inbox_context(self):
        response = self.client.get(reverse("lead-list"))
        self.assertEqual(response.status_code, 200)
        item = response.data[0]
        self.assertEqual(item["source_display"], "Viber")
        self.assertEqual(item["interested_property"]["id"], self.property.id)
        self.assertEqual(item["site_visits_count"], 1)
        self.assertEqual(item["offers_count"], 1)
        self.assertEqual(item["documents_count"], 1)

    def test_workspace_returns_complete_lead_record(self):
        response = self.client.get(
            reverse("lead-workspace", kwargs={"lead_id": self.lead.id})
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["lead"]["assigned_agent_name"], "Inbox Agent")
        self.assertIsNotNone(response.data["lead"]["last_contacted_at"])
        self.assertEqual(response.data["interactions"][0]["direction"], "inbound")
        self.assertEqual(response.data["site_visits"][0]["property"], self.property.id)
        self.assertEqual(response.data["deals"][0]["stage"], "negotiation")
        self.assertEqual(response.data["offers"][0]["status"], "countered")
        self.assertEqual(response.data["documents"][0]["title"], "Buyer citizenship")

    def test_documents_can_be_attached_directly_to_a_lead(self):
        response = self.client.post(
            reverse("lead-document-list", kwargs={"lead_id": self.lead.id}),
            {
                "title": "Offer letter",
                "category": "contract",
                "file": SimpleUploadedFile("offer.pdf", b"%PDF-offer", "application/pdf"),
                "description": "Signed buyer offer",
            },
            format="multipart",
        )
        self.assertEqual(response.status_code, 201)
        self.assertTrue(Document.objects.filter(lead=self.lead, title="Offer letter").exists())

    def test_explicit_inquiry_sources_are_accepted(self):
        for source in ["phone", "walk_in", "whatsapp", "viber", "referral", "property_portal"]:
            response = self.client.post(
                reverse("lead-list"),
                {
                    "full_name": f"{source} customer",
                    "phone": f"98{Lead.objects.count():08d}",
                    "source": source,
                },
                format="json",
            )
            self.assertEqual(response.status_code, 201, response.data)

    def test_agents_cannot_open_another_agents_workspace(self):
        other_agent = AgencyUser.objects.create_user(
            email="other-agent@example.com",
            password="Password123",
            full_name="Other Agent",
            agency=self.agency,
            role="agent",
        )
        self.lead.assigned_agent = other_agent
        self.lead.save(update_fields=["assigned_agent", "updated_at"])
        self.client.force_authenticate(self.agent)
        response = self.client.get(
            reverse("lead-workspace", kwargs={"lead_id": self.lead.id})
        )
        self.assertEqual(response.status_code, 404)
